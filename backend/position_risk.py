"""
Live position risk analysis + EXIT SIGNAL engine.

Cross-references your ACTUAL live Zerodha positions (not just auto-trader
trades — every open NIFTY option position, however it was opened) against
the current CAS signal AND live market data (spot price, actual strike,
days-to-expiry) to produce a definitive EXIT / HOLD / BOOK_PROFIT
recommendation for each position — not just generic alerts.

Exit signal logic (single-leg CE/PE positions):
  - SIGNAL_FLIPPED: live directional signal has flipped against your
    position's implied direction (holding CE but signal turned BEARISH, etc)
  - SHORT_ITM_RISK: for a SHORT (written) position, spot has moved to/through
    the actual strike (real moneyness, not just P&L) — assignment/large-loss
    risk on a short option that isn't hedged
  - DEEP_LOSS: down beyond a configurable stop-loss threshold
  - NEAR_TARGET: up beyond a configurable target threshold -> BOOK_PROFIT
  - EXPIRY_THETA_RISK: DTE=0 (expiry day) + still OTM+far from ITM with
    negligible time value left — theta has already eaten most of the edge
  - HOLD: none of the above triggered

Exit signal logic (iron condor 4-leg shape, detected via the existing
get_live_iron_condor_status() heuristic):
  - IC_BREACH_UPSIDE / IC_BREACH_DOWNSIDE: live spot has crossed either
    short strike — the position's max-loss zone has been entered
  - IC_NEAR_BREACH: spot within a configurable buffer % of either short
    strike — early warning before the breach happens
  - HOLD: spot comfortably between both short strikes

This is READ-ONLY / advisory — it never places or modifies any order. It's
purely a monitoring/alerting + recommendation layer on top of whatever
positions exist in your account (whether opened manually, via the Dry Run
feature, or via the Auto-Trader).
"""
import logging
import re
from datetime import datetime

import zerodha_client
import cas_service
import iron_condor as iron_condor_module
from nse_options import get_nse_options_data

logger = logging.getLogger(__name__)

# Risk alert thresholds (not hidden — surfaced in the API response so the
# UI can explain exactly why an alert/recommendation fired)
DEEP_LOSS_PCT_THRESHOLD = -25.0    # position down >25% of entry value -> EXIT
NEAR_TARGET_PCT_THRESHOLD = 40.0   # position up >40% of entry value -> BOOK_PROFIT
IC_BREACH_BUFFER_PCT = 0.5         # within 0.5% of a short strike -> near-breach warning


def _extract_option_details(tradingsymbol: str) -> dict:
    """
    Parse a Zerodha NIFTY option tradingsymbol like 'NIFTY24D0424200CE' into
    its option type (CE/PE) AND actual strike price — the strike is the
    numeric block immediately before CE/PE. Best-effort; falls back to
    strike=None if the pattern doesn't match (never raises).
    """
    option_type = None
    strike = None
    if tradingsymbol.endswith("CE"):
        option_type = "CE"
    elif tradingsymbol.endswith("PE"):
        option_type = "PE"

    if option_type:
        m = re.search(r"(\d+)(CE|PE)$", tradingsymbol)
        if m:
            try:
                strike = int(m.group(1))
            except ValueError:
                strike = None

    return {"option_type": option_type, "strike": strike}


def _get_live_spot_and_dte():
    """
    Fetches the live NIFTY spot price and days-to-expiry directly from the
    NSE option chain — the same source of truth used for the iron condor
    strike suggestions, so the exit signal here reasons about the SAME live
    market data (not a stale/cached signal-only value). Returns (None, None)
    on any failure rather than raising.
    """
    try:
        chain = get_nse_options_data()
        if chain:
            return chain.get("spot_price"), chain.get("days_to_expiry")
    except Exception as e:
        logger.warning(f"position_risk: could not fetch live spot/DTE: {e}")
    return None, None


def _single_leg_exit_signal(
    option_type: str,
    strike: int,
    quantity: int,
    pnl_pct: float,
    spot: float,
    dte: float,
    current_bias: str,
    signal_ok: bool,
    big_move_risk: str,
) -> dict:
    """
    Computes a definitive recommendation for a single-leg (non-IC) NIFTY
    option position, using REAL moneyness (live spot vs actual strike) —
    not just P&L — combined with the live directional signal and DTE.

    Returns {"recommendation": "EXIT"|"BOOK_PROFIT"|"HOLD"|"MONITOR",
             "reasons": [...]} — reasons is a list of the specific triggers,
    so the UI can show exactly why (multiple can fire at once).
    """
    reasons = []
    recommendation = "HOLD"
    is_short = quantity < 0  # negative quantity = written/sold option

    # Real moneyness relative to the ACTUAL strike, not just entry price
    moneyness_pct = None
    if spot and strike:
        if option_type == "CE":
            moneyness_pct = (spot - strike) / strike * 100  # positive = ITM
        else:  # PE
            moneyness_pct = (strike - spot) / strike * 100  # positive = ITM

    # 1) Signal has flipped against this position's implied direction
    if signal_ok and current_bias in ("BULLISH", "BEARISH") and option_type:
        position_direction = "BULLISH" if option_type == "CE" else "BEARISH"
        if is_short:
            # A SHORT position benefits from the OPPOSITE of its option-type
            # direction (e.g. short CE wants price to stay below/fall) — so
            # for shorts, a signal matching the option's own direction is
            # the adverse case.
            adverse = current_bias == position_direction
        else:
            adverse = current_bias != position_direction
        if adverse:
            reasons.append({
                "type": "SIGNAL_FLIPPED",
                "message": (
                    f"Live signal is {current_bias}, which is adverse to your "
                    f"{'short' if is_short else 'long'} {option_type} position."
                ),
            })
            recommendation = "EXIT"

    # 2) Real ITM risk for a SHORT (written) option — this is the actual
    # danger zone for a naked/uncovered short: assignment + uncapped loss
    if is_short and moneyness_pct is not None and moneyness_pct > 0:
        reasons.append({
            "type": "SHORT_ITM_RISK",
            "message": (
                f"Your short {option_type} (strike {strike}) is now "
                f"{moneyness_pct:.2f}% IN THE MONEY at spot {spot} — real "
                f"assignment/loss risk, not just a P&L number."
            ),
        })
        recommendation = "EXIT"

    # 3) Big-move risk is HIGH
    if big_move_risk == "HIGH":
        reasons.append({
            "type": "HIGH_BIGMOVE_RISK",
            "message": "Big-move risk for today's closing window is currently HIGH.",
        })
        if recommendation == "HOLD":
            recommendation = "MONITOR"

    # 4) Deep loss (P&L based, backstop even if moneyness calc unavailable)
    if pnl_pct <= DEEP_LOSS_PCT_THRESHOLD:
        reasons.append({
            "type": "DEEP_LOSS",
            "message": f"Position is down {pnl_pct:.1f}% from entry value.",
        })
        recommendation = "EXIT"

    # 5) Near target — profit-booking nudge (only relevant if nothing worse fired)
    if pnl_pct >= NEAR_TARGET_PCT_THRESHOLD and recommendation not in ("EXIT",):
        reasons.append({
            "type": "NEAR_TARGET",
            "message": f"Position is up {pnl_pct:.1f}% from entry value.",
        })
        recommendation = "BOOK_PROFIT"

    # 6) Expiry-day theta risk — OTM position with essentially no time left
    if dte is not None and dte < 0.5 and moneyness_pct is not None and moneyness_pct < -1.0 and not is_short:
        reasons.append({
            "type": "EXPIRY_THETA_RISK",
            "message": (
                f"Today is expiry day and this long {option_type} is "
                f"{abs(moneyness_pct):.2f}% OTM — little time value left, "
                f"likely to expire worthless if spot doesn't move fast."
            ),
        })
        if recommendation == "HOLD":
            recommendation = "MONITOR"

    return {"recommendation": recommendation, "reasons": reasons, "moneyness_pct": round(moneyness_pct, 2) if moneyness_pct is not None else None}


def get_live_positions_with_risk() -> dict:
    """
    Returns all open NIFTY option positions (from `net` positions, i.e. the
    position as of now including today's trades) enriched with:
      - live P&L (rupees and %)
      - actual strike (parsed from the tradingsymbol)
      - a definitive EXIT / BOOK_PROFIT / MONITOR / HOLD recommendation,
        computed from LIVE spot price + actual strike + DTE + the live
        directional signal (not just a generic P&L threshold)
      - the underlying reasons for that recommendation

    If the open positions form a 4-leg iron-condor shape, ALSO includes a
    separate `iron_condor_exit_signal` block with IC-specific breach logic
    (spot vs actual short strikes, not just P&L).

    Returns a dict: {"success": bool, "positions": [...], "signal_context": {...}}
    On any error (Zerodha not connected, etc.) returns success=False with a
    clear message — never raises.
    """
    if not zerodha_client.is_configured():
        return {
            "success": False,
            "message": "Zerodha not configured — no live positions to show.",
            "positions": [],
        }

    try:
        positions_data = zerodha_client.get_positions()
    except RuntimeError as e:
        return {"success": False, "message": str(e), "positions": []}
    except Exception as e:
        logger.error(f"position_risk: failed to fetch positions: {e}")
        return {"success": False, "message": f"Could not fetch positions: {e}", "positions": []}

    net_positions = positions_data.get("net", [])
    nifty_positions = [
        p for p in net_positions
        if p.get("exchange") == "NFO"
        and "NIFTY" in (p.get("tradingsymbol") or "")
        and p.get("quantity", 0) != 0
    ]

    # Fetch the current CAS signal ONCE (not per-position) — it's the same
    # signal context for every position at this instant. Use the cached
    # result (force_refresh=False) so this stays fast even with many
    # positions or frequent polling.
    try:
        signal = cas_service.get_live_cas_signal(force_refresh=False)
    except Exception as e:
        logger.error(f"position_risk: failed to fetch CAS signal: {e}")
        signal = {"success": False}

    signal_ok = signal.get("success", False)
    current_bias = signal.get("directional_bias") if signal_ok else None
    big_move_risk = signal.get("risk_level") if signal_ok else None

    # Live spot + DTE — the actual market data used for moneyness/breach
    # calculations below, fetched once and reused for every position.
    live_spot, live_dte = _get_live_spot_and_dte()

    enriched = []
    for p in nifty_positions:
        tradingsymbol = p.get("tradingsymbol", "")
        details = _extract_option_details(tradingsymbol)
        option_type = details["option_type"]
        strike = details["strike"]

        quantity = p.get("quantity", 0)
        avg_price = p.get("average_price", 0)
        last_price = p.get("last_price", 0)
        pnl = p.get("pnl", 0)

        # % P&L relative to position value at entry (avoid div-by-zero)
        entry_value = abs(avg_price * quantity)
        pnl_pct = (pnl / entry_value * 100) if entry_value > 0 else 0.0

        exit_signal = _single_leg_exit_signal(
            option_type=option_type,
            strike=strike,
            quantity=quantity,
            pnl_pct=pnl_pct,
            spot=live_spot,
            dte=live_dte,
            current_bias=current_bias,
            signal_ok=signal_ok,
            big_move_risk=big_move_risk,
        )

        # Keep the existing `alerts` shape for backward-compat with any
        # existing frontend code, built directly from the exit_signal reasons.
        severity_map = {"EXIT": "danger", "BOOK_PROFIT": "info", "MONITOR": "warning", "HOLD": "info"}
        alerts = [
            {
                "severity": severity_map.get(exit_signal["recommendation"], "info"),
                "type": r["type"],
                "message": r["message"],
            }
            for r in exit_signal["reasons"]
        ]

        enriched.append({
            "tradingsymbol": tradingsymbol,
            "option_type": option_type,
            "strike": strike,
            "quantity": quantity,
            "average_price": avg_price,
            "last_price": last_price,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "product": p.get("product"),
            "recommendation": exit_signal["recommendation"],
            "moneyness_pct": exit_signal["moneyness_pct"],
            "alerts": alerts,
        })

    # ── Iron condor-specific exit signal (if a 4-leg IC shape is detected) ──
    ic_exit_signal = None
    try:
        ic_status = iron_condor_module.get_live_iron_condor_status()
        if ic_status.get("detected"):
            spot = ic_status.get("spot_price") or live_spot
            short_call_strike = ic_status.get("short_call_strike")
            short_put_strike = ic_status.get("short_put_strike")

            recommendation = "HOLD"
            reasons = []
            if spot and short_call_strike and short_put_strike:
                if spot >= short_call_strike:
                    recommendation = "EXIT"
                    reasons.append({
                        "type": "IC_BREACH_UPSIDE",
                        "message": (
                            f"Spot ({spot}) has reached/crossed the short call strike "
                            f"({short_call_strike}) — the defined max-loss zone on the "
                            f"upside has been entered."
                        ),
                    })
                elif spot <= short_put_strike:
                    recommendation = "EXIT"
                    reasons.append({
                        "type": "IC_BREACH_DOWNSIDE",
                        "message": (
                            f"Spot ({spot}) has reached/crossed the short put strike "
                            f"({short_put_strike}) — the defined max-loss zone on the "
                            f"downside has been entered."
                        ),
                    })
                else:
                    call_buffer_pct = (short_call_strike - spot) / spot * 100
                    put_buffer_pct = (spot - short_put_strike) / spot * 100
                    nearest_buffer = min(call_buffer_pct, put_buffer_pct)
                    if nearest_buffer < IC_BREACH_BUFFER_PCT:
                        recommendation = "MONITOR"
                        reasons.append({
                            "type": "IC_NEAR_BREACH",
                            "message": (
                                f"Spot ({spot}) is within {nearest_buffer:.2f}% of a short "
                                f"strike (call buffer {call_buffer_pct:.2f}%, put buffer "
                                f"{put_buffer_pct:.2f}%) — consider adjusting or closing "
                                f"before a breach."
                            ),
                        })

            ic_exit_signal = {
                "detected": True,
                "recommendation": recommendation,
                "reasons": reasons,
                "spot_price": spot,
                "short_call_strike": short_call_strike,
                "short_put_strike": short_put_strike,
                "total_pnl": ic_status.get("total_pnl"),
            }
    except Exception as e:
        logger.warning(f"position_risk: iron condor exit signal check failed: {e}")

    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "positions": enriched,
        "position_count": len(enriched),
        "signal_context": {
            "available": signal_ok,
            "directional_bias": current_bias,
            "risk_level": big_move_risk,
            "live_spot": live_spot,
            "live_dte": live_dte,
        },
        "iron_condor_exit_signal": ic_exit_signal,
    }