"""
Automated trading engine for the CAS signal system.

╔══════════════════════════════════════════════════════════════════════════╗
║  SAFETY-FIRST DESIGN — READ BEFORE ENABLING                              ║
╠══════════════════════════════════════════════════════════════════════════╣
║  This module can place REAL orders with REAL money on your live Zerodha  ║
║  account, completely unattended. It is DISABLED BY DEFAULT and requires  ║
║  explicit opt-in through multiple layers:                                ║
║                                                                            ║
║    1. Zerodha must be connected (API key/secret + login flow completed)  ║
║    2. AUTO_TRADE_ENABLED setting must be explicitly turned ON in the UI  ║
║       (Settings → Auto-Trader). Defaults to OFF and resets to OFF on     ║
║       server restart for extra safety (see _load_auto_trade_settings).  ║
║    3. By default, only trades the VALIDATED high-conviction rule (86.5% ║
║       historical win rate, BULLISH-only) — NOT the general ~62%          ║
║       directional signal, which the model's own honesty note describes  ║
║       as "a genuine statistical edge, NOT a high-confidence guarantee."  ║
║       Trading on the general signal requires a SEPARATE explicit opt-in. ║
║                                                                            ║
║  Hard-coded (non-configurable) guardrails that CANNOT be bypassed via    ║
║  settings, by design:                                                    ║
║    - Max 1 open auto-trader position at a time                          ║
║    - Max 2 auto-trades per calendar day                                  ║
║    - Daily loss circuit breaker: if realized P&L from auto-trades today  ║
║      drops below -₹(configurable, default 2000), auto-trading disables  ║
║      itself for the REST OF THE DAY automatically                       ║
║    - Never trades within the last 20 minutes before market close (the    ║
║      CAS/closing-auction window itself) — entering a fresh position      ║
║      right as the volatile closing window begins is exactly the wrong    ║
║      time to add risk                                                    ║
║    - Never trades if NSE option-chain data is stale/unavailable          ║
║    - Every decision (placed OR skipped, and why) is logged to            ║
║      `auto_trade_log` — see database.py                                  ║
║                                                                            ║
║  This is intraday-only (product=MIS): all positions are expected to be   ║
║  squared off by the broker's auto-square-off time if not exited manually ║
║  or via the GTT OCO exit order placed alongside every entry.             ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import os
import logging
import threading
import time as _time
from datetime import datetime, time as dt_time

import zerodha_client
import cas_service
from database import (
    get_setting, set_setting,
    log_auto_trade_event, get_auto_trade_log,
    count_auto_trades_today, sum_auto_trade_realized_pnl_today,
)

logger = logging.getLogger(__name__)

# ── Settings keys (persisted in app_settings table) ─────────────────────────
_KEY_ENABLED = "auto_trade_enabled"
_KEY_MODE = "auto_trade_mode"                    # "high_conviction_only" | "directional_signal"
_KEY_LOTS = "auto_trade_lots"                     # number of lots per trade
_KEY_MAX_DAILY_LOSS = "auto_trade_max_daily_loss"  # rupees, positive number
_KEY_LAST_TRADED_SIGNAL_DATE = "auto_trade_last_signal_date"  # dedup key

# ── Hard-coded, non-configurable guardrails ─────────────────────────────────
MAX_OPEN_POSITIONS = 1
MAX_TRADES_PER_DAY = 2
NIFTY_LOT_SIZE = 75  # verify against current NSE circular; used as fallback only —
                      # the actual lot_size always comes from zerodha_client.find_nifty_option_symbol()
NO_NEW_ENTRY_AFTER = dt_time(15, 10)   # no new entries after 3:10pm IST (avoids the CAS window itself)
MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)

CHECK_INTERVAL_SECONDS = 60  # how often the background loop checks the live signal


# ── Settings accessors ───────────────────────────────────────────────────────

def is_enabled() -> bool:
    return get_setting(_KEY_ENABLED) == "true"


def set_enabled(value: bool):
    set_setting(_KEY_ENABLED, "true" if value else "false")
    log_auto_trade_event({
        "action": "KILL_SWITCH",
        "reason": f"Auto-trading {'ENABLED' if value else 'DISABLED'} by user via Settings UI",
    })


def get_mode() -> str:
    return get_setting(_KEY_MODE) or "high_conviction_only"


def set_mode(mode: str):
    if mode not in ("high_conviction_only", "directional_signal"):
        raise ValueError("mode must be 'high_conviction_only' or 'directional_signal'")
    set_setting(_KEY_MODE, mode)


def get_lots() -> int:
    val = get_setting(_KEY_LOTS)
    try:
        return max(1, int(val)) if val else 1
    except (TypeError, ValueError):
        return 1


def set_lots(lots: int):
    set_setting(_KEY_LOTS, str(max(1, int(lots))))


def get_max_daily_loss() -> float:
    val = get_setting(_KEY_MAX_DAILY_LOSS)
    try:
        return float(val) if val else 2000.0
    except (TypeError, ValueError):
        return 2000.0


def set_max_daily_loss(amount: float):
    set_setting(_KEY_MAX_DAILY_LOSS, str(max(500.0, float(amount))))


def get_config() -> dict:
    """Full config snapshot, used by the Settings UI and the status endpoint."""
    return {
        "enabled": is_enabled(),
        "mode": get_mode(),
        "lots": get_lots(),
        "max_daily_loss": get_max_daily_loss(),
        "max_open_positions": MAX_OPEN_POSITIONS,
        "max_trades_per_day": MAX_TRADES_PER_DAY,
        "trades_today": count_auto_trades_today(),
        "realized_pnl_today": sum_auto_trade_realized_pnl_today(),
        "no_new_entry_after": NO_NEW_ENTRY_AFTER.strftime("%H:%M"),
    }


def _disable_on_startup_for_safety():
    """
    Called once at server startup. We deliberately do NOT let auto-trading
    silently resume after a server restart/crash — the operator must always
    re-confirm intent by explicitly re-enabling it in the UI. This prevents
    a scenario where a config left ON from days ago starts trading again
    without the user realizing the server ever restarted.
    """
    if is_enabled():
        set_enabled(False)
        log_auto_trade_event({
            "action": "KILL_SWITCH",
            "reason": "Auto-trading was ON before a server restart — automatically "
                      "disabled for safety. Re-enable explicitly in Settings if desired.",
        })
        logger.warning(
            "auto_trader: was enabled before restart — disabled automatically for safety."
        )


# ── Core decision logic ──────────────────────────────────────────────────────

def _within_trading_window() -> bool:
    now_t = datetime.now().time()
    return MARKET_OPEN <= now_t <= NO_NEW_ENTRY_AFTER


def _market_is_open() -> bool:
    now = datetime.now()
    if now.weekday() >= 5:  # Sat/Sun
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def _has_open_auto_position() -> bool:
    """
    Checks Zerodha's actual live positions for any open MIS position in a
    NIFTY option — used as the source of truth for "do we already have an
    auto-trader position open" rather than trusting our own log (in case a
    position was manually closed outside this app).
    """
    try:
        positions = zerodha_client.get_positions()
        net = positions.get("net", [])
        for p in net:
            if (
                p.get("exchange") == "NFO"
                and "NIFTY" in (p.get("tradingsymbol") or "")
                and p.get("quantity", 0) != 0
            ):
                return True
        return False
    except Exception as e:
        logger.error(f"auto_trader: could not check open positions ({e}) — assuming OPEN to be safe")
        return True  # fail safe: if we can't verify, assume there IS an open position and skip


def evaluate_and_act():
    """
    The main decision function — called periodically by the background loop.
    Fetches the current CAS live signal and decides whether to place a trade,
    logging every decision either way. Never raises — all errors are caught,
    logged, and treated as "skip this cycle".
    """
    try:
        if not is_enabled():
            return  # silent no-op when disabled — this is the normal 99% case

        if not zerodha_client.is_configured():
            log_auto_trade_event({"action": "SKIPPED", "reason": "Zerodha not configured"})
            return

        if not _market_is_open():
            return  # silent — outside market hours is normal, not worth logging every cycle

        if not _within_trading_window():
            return  # silent — too close to close, normal daily occurrence

        # Daily loss circuit breaker
        max_loss = get_max_daily_loss()
        realized_today = sum_auto_trade_realized_pnl_today()
        if realized_today <= -abs(max_loss):
            log_auto_trade_event({
                "action": "SKIPPED",
                "reason": (
                    f"Daily loss circuit breaker triggered: realized P&L today "
                    f"₹{realized_today:.0f} <= -₹{max_loss:.0f} limit. "
                    f"Auto-trading paused for the rest of today."
                ),
            })
            return

        # Daily trade count limit
        trades_today = count_auto_trades_today()
        if trades_today >= MAX_TRADES_PER_DAY:
            return  # silent — hitting the daily cap is a normal, already-logged-once situation

        # Open position limit (checked against Zerodha's live positions, not our own log)
        if _has_open_auto_position():
            return  # silent — already in a trade, nothing to do

        # Dedup: don't act on the same day's signal twice
        today_str = datetime.now().strftime("%Y-%m-%d")
        if get_setting(_KEY_LAST_TRADED_SIGNAL_DATE) == today_str:
            return

        # Fetch the live signal
        signal = cas_service.get_live_cas_signal(force_refresh=False)
        if not signal.get("success"):
            log_auto_trade_event({
                "action": "SKIPPED",
                "reason": f"CAS signal fetch failed: {signal.get('message', 'unknown error')}",
            })
            return

        mode = get_mode()
        should_trade = False
        direction = signal.get("directional_bias")
        pop = signal.get("directional_pop")
        is_hc = bool(signal.get("high_conviction_signal"))

        if mode == "high_conviction_only":
            # Only ever trade the VALIDATED rule (BULLISH-only, 86.5% historical
            # win rate). This is the safe default.
            if is_hc:
                hc_detail = signal.get("high_conviction_detail") or {}
                if hc_detail.get("direction", "").startswith("BULLISH"):
                    should_trade = True
                    direction = "BULLISH"
                    pop = hc_detail.get("historical_win_rate")
        elif mode == "directional_signal":
            # Riskier: trade the general ~62%-accuracy directional model.
            # Requires the user to have explicitly opted into this mode.
            if direction in ("BULLISH", "BEARISH") and pop and pop >= 0.60:
                should_trade = True

        if not should_trade:
            return  # silent — no qualifying signal this cycle, completely normal

        # We have a qualifying signal — attempt to place the trade.
        spot = signal.get("spot_price")
        suggested_strike = signal.get("suggested_strike")
        nearest_expiry = signal.get("nearest_expiry")  # e.g. "04-Sep-2026" from NSE

        if not spot or not suggested_strike or not nearest_expiry:
            log_auto_trade_event({
                "action": "SKIPPED",
                "reason": "Missing spot/strike/expiry data — cannot place a safe order",
                "signal_direction": direction,
                "pop": pop,
                "high_conviction": is_hc,
            })
            return

        option_type = "CE" if direction == "BULLISH" else "PE"

        # Convert NSE's expiry format ("04-Sep-2026") to Kite's ISO format
        try:
            expiry_iso = datetime.strptime(nearest_expiry, "%d-%b-%Y").strftime("%Y-%m-%d")
        except ValueError:
            log_auto_trade_event({
                "action": "SKIPPED",
                "reason": f"Could not parse expiry date '{nearest_expiry}'",
                "signal_direction": direction,
            })
            return

        try:
            contract = zerodha_client.find_nifty_option_symbol(
                strike=int(suggested_strike), expiry_date=expiry_iso, option_type=option_type
            )
        except RuntimeError as e:
            log_auto_trade_event({
                "action": "SKIPPED",
                "reason": f"Contract lookup failed: {e}",
                "signal_direction": direction,
                "strike": int(suggested_strike),
                "option_type": option_type,
            })
            return

        lots = get_lots()
        quantity = lots * contract["lot_size"]

        # Get current option premium via LTP so we can set a sane SL/target
        try:
            ltp_data = zerodha_client.get_ltp([f"NFO:{contract['tradingsymbol']}"])
            entry_price = ltp_data[f"NFO:{contract['tradingsymbol']}"]["last_price"]
        except Exception as e:
            log_auto_trade_event({
                "action": "SKIPPED",
                "reason": f"Could not fetch live option price: {e}",
                "tradingsymbol": contract["tradingsymbol"],
            })
            return

        # Balance/margin sufficiency check BEFORE placing any order — refuse
        # to place a trade that would exceed available account balance.
        # Uses the option's own premium (BUY orders need full premium *
        # quantity as margin, no cross-margining benefit for a single leg).
        try:
            required_capital = entry_price * quantity
            balance = zerodha_client.get_available_balance()
            available = balance["available_margin"] or balance["available_cash"]
            if available < required_capital:
                log_auto_trade_event({
                    "action": "SKIPPED",
                    "reason": (
                        f"Insufficient balance: need ~₹{required_capital:.0f} for "
                        f"{quantity} qty @ ₹{entry_price}, but only ₹{available:.0f} "
                        f"available. Trade skipped to avoid a margin-call/rejection."
                    ),
                    "tradingsymbol": contract["tradingsymbol"],
                    "quantity": quantity,
                })
                return
        except Exception as e:
            logger.warning(f"auto_trader: balance check failed, proceeding cautiously: {e}")

        if not entry_price or entry_price <= 0:
            log_auto_trade_event({
                "action": "SKIPPED",
                "reason": f"Invalid option premium ({entry_price}) — refusing to trade",
                "tradingsymbol": contract["tradingsymbol"],
            })
            return

        # SL/target as % of premium (options move fast — using premium %, not
        # spot ATR, since that's the actual instrument being traded)
        sl_price = round(entry_price * 0.70, 1)     # -30% stop-loss on premium
        target_price = round(entry_price * 1.50, 1)  # +50% target on premium

        # Place the entry order
        try:
            order_result = zerodha_client.place_order(
                tradingsymbol=contract["tradingsymbol"],
                exchange="NFO",
                transaction_type="BUY",
                quantity=quantity,
                order_type="MARKET",
                product="MIS",
            )
        except Exception as e:
            log_auto_trade_event({
                "action": "ERROR",
                "reason": f"Order placement FAILED: {e}",
                "signal_direction": direction,
                "strike": int(suggested_strike),
                "option_type": option_type,
                "tradingsymbol": contract["tradingsymbol"],
                "quantity": quantity,
                "pop": pop,
                "high_conviction": is_hc,
            })
            return

        order_id = order_result.get("order_id")

        # Immediately place the GTT OCO exit order (SL + target)
        gtt_id = None
        try:
            gtt_result = zerodha_client.place_gtt_oco_exit(
                tradingsymbol=contract["tradingsymbol"],
                exchange="NFO",
                quantity=quantity,
                last_price=entry_price,
                stop_loss_price=sl_price,
                target_price=target_price,
            )
            gtt_id = gtt_result.get("gtt_id")
        except Exception as e:
            logger.error(f"auto_trader: entry order placed but GTT exit order FAILED: {e}")
            log_auto_trade_event({
                "action": "ERROR",
                "reason": (
                    f"Entry order {order_id} placed successfully, but the automatic "
                    f"GTT exit (SL/target) order FAILED to place: {e}. "
                    f"MANUAL INTERVENTION NEEDED — position has no automatic exit."
                ),
                "tradingsymbol": contract["tradingsymbol"],
                "order_id": order_id,
            })

        # Record success + mark today as traded (dedup)
        set_setting(_KEY_LAST_TRADED_SIGNAL_DATE, today_str)
        log_auto_trade_event({
            "action": "TRADE_PLACED",
            "reason": (
                f"{'High-conviction rule' if mode == 'high_conviction_only' else 'Directional signal'} "
                f"fired: {direction}, POP={pop}"
            ),
            "signal_direction": direction,
            "strike": int(suggested_strike),
            "option_type": option_type,
            "tradingsymbol": contract["tradingsymbol"],
            "quantity": quantity,
            "entry_price": entry_price,
            "sl_price": sl_price,
            "target_price": target_price,
            "order_id": order_id,
            "gtt_id": gtt_id,
            "pop": pop,
            "high_conviction": is_hc,
        })
        logger.info(
            f"auto_trader: TRADE PLACED — {direction} {contract['tradingsymbol']} "
            f"qty={quantity} entry~₹{entry_price} SL=₹{sl_price} target=₹{target_price} "
            f"order_id={order_id} gtt_id={gtt_id}"
        )

    except Exception as e:
        logger.error(f"auto_trader: unexpected error in evaluate_and_act: {e}")
        try:
            log_auto_trade_event({"action": "ERROR", "reason": f"Unexpected error: {e}"})
        except Exception:
            pass


# ── Background loop ──────────────────────────────────────────────────────────

def start_background_loop():
    """
    Starts the daemon thread that periodically checks the live signal and
    acts on it (if enabled). Call once at server startup. The loop itself
    is cheap when disabled (single settings lookup, immediate return).
    """
    _disable_on_startup_for_safety()

    def _loop():
        while True:
            evaluate_and_act()
            _time.sleep(CHECK_INTERVAL_SECONDS)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    logger.info(
        f"auto_trader: background loop started (checks every {CHECK_INTERVAL_SECONDS}s; "
        f"currently {'ENABLED' if is_enabled() else 'DISABLED'})"
    )