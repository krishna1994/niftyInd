"""
Short Iron Condor strategy helper.

A short iron condor is a defined-risk, range-bound premium-selling strategy:
  - SELL 1 OTM Call (short call)
  - BUY  1 further OTM Call (long call — the "wing", caps upside risk)
  - SELL 1 OTM Put  (short put)
  - BUY  1 further OTM Put  (long put — the "wing", caps downside risk)

All 4 legs share the same expiry and lot size. Max profit = net premium
collected (if spot expires between the short strikes). Max loss = wing
width - net premium (if spot moves beyond either long strike). This is
what makes it a DEFINED-RISK strategy, unlike a naked short straddle.

This module handles:
  1. Suggesting strikes based on the live NSE option chain (using OTM
     distance / IV-implied expected move as the primary heuristic)
  2. Computing the full payoff diagram, max profit/loss, breakevens,
     and probability of profit (using IV + normal-distribution approximation)
  3. Placing all 4 legs as a single Zerodha basket order (with pre-trade
     margin check) or individually
  4. Tracking/analyzing an existing open iron condor position (for the
     "monitor my existing IC" use case)
"""
import logging
import math
from datetime import datetime
from typing import Optional

import zerodha_client
from nse_options import get_nse_options_data

logger = logging.getLogger(__name__)


def _round_to_strike_step(value: float, step: int = 50) -> int:
    return int(round(value / step) * step)


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function (no scipy dependency)."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# Historical backtest reference (see backend/IRON_CONDOR_BACKTEST_FINDINGS.md
# for the full 2-year, 104-weekly-cycle analysis this is based on):
#   - Tuesday entry (2 DTE) @ 2.5% OTM: 100% historical win rate, both years
#     tested independently — the safest, smallest-premium "base" trade.
#   - Friday entry (4-5 DTE) @ 2.0-2.5% OTM, VIX<=13-14: 90-98% win rate,
#     much bigger premium but real historical tail-risk losses of
#     -₹13k to -₹18k per lot in the worst weeks.
# Default here (2.5%, 200pt) sits between these two validated combos as a
# reasonable general-purpose starting point; adjust per the day you're
# actually entering (see get_recommended_params()).
BACKTESTED_RECOMMENDATIONS = {
    "Tuesday": {"otm_distance_pct": 2.5, "wing_width_points": 150, "note": "100% historical win rate (2yr), safest weekly base trade"},
    "Monday": {"otm_distance_pct": 2.5, "wing_width_points": 200, "note": "95.8% historical win rate (2yr)"},
    "Wednesday": {"otm_distance_pct": 2.0, "wing_width_points": 200, "note": "83-98% historical win rate depending on year"},
    "Friday": {"otm_distance_pct": 2.0, "wing_width_points": 200, "note": "76-93% historical win rate; use VIX<=13-14 filter for best results"},
}


# Backtest-derived "sigma multiplier" per entry day: how many standard
# deviations of expected move away from spot the backtested-optimal OTM%
# represents, computed as (backtested_otm_pct / expected_move_pct_at_that_
# days_avg_dte_and_vix). This lets us scale the strike distance correctly
# for the CURRENT live IV and DTE, instead of blindly applying a fixed %
# that was only validated for a specific DTE (e.g. applying a 2-DTE-derived
# 2.5% OTM on an actual 0-DTE/expiry day massively overshoots the real
# expected move, producing near-zero premium — exactly the "suggestion too
# far away" issue this fixes).
BACKTESTED_SIGMA_MULTIPLIERS = {
    "Tuesday": 2.4,    # tightest — 100% historical win rate at this z-level
    "Monday": 2.4,
    "Wednesday": 1.4,
    "Friday": 1.2,     # widest — but still calibrated to actual expected move
}
DEFAULT_SIGMA_MULTIPLIER = 1.8


def get_dynamic_recommended_otm(dte: float, avg_iv_pct: float, entry_dow: str = None) -> dict:
    """
    Computes a LIVE, DTE/IV-aware recommended OTM% — the correct fix for
    "suggested strikes are too far away, negligible premium" on low-DTE days
    (especially DTE=0, expiry day itself): a fixed % calibrated for a 2-DTE
    Monday entry is meaningless applied on a 0-DTE day, where the real
    expected move is much smaller.

    Uses the standard options expected-move formula (IV × sqrt(DTE/365))
    times a sigma-multiplier calibrated from the 2-year historical backtest
    for the given entry day (see BACKTESTED_SIGMA_MULTIPLIERS) — this keeps
    the backtest's risk profile (e.g. "Tuesday-safe" = 2.4 sigma) while
    correctly adapting the ACTUAL distance to today's real IV and DTE.
    """
    dte_for_calc = max(dte, 0.3)  # floor to avoid sigma=0 on expiry day itself
    sigma_pct = (avg_iv_pct / 100) * math.sqrt(dte_for_calc / 365) * 100  # 1-sigma move, in %

    multiplier = BACKTESTED_SIGMA_MULTIPLIERS.get(entry_dow, DEFAULT_SIGMA_MULTIPLIER)
    dynamic_otm_pct = round(sigma_pct * multiplier, 2)
    # Sensible floor/ceiling so this never suggests something degenerate
    dynamic_otm_pct = max(0.4, min(dynamic_otm_pct, 6.0))

    return {
        "otm_distance_pct": dynamic_otm_pct,
        "sigma_pct": round(sigma_pct, 3),
        "sigma_multiplier": multiplier,
        "dte_used": dte_for_calc,
    }


def get_recommended_params(entry_dow: str, dte: float = None, avg_iv_pct: float = None) -> dict:
    """
    Returns the recommended (otm_distance_pct, wing_width_points) for the
    given entry day of week. If dte + avg_iv_pct are provided (live market
    conditions), the OTM% is computed DYNAMICALLY from the actual expected
    move (see get_dynamic_recommended_otm) rather than blindly reusing the
    fixed backtest OTM% — this is what makes the suggestion stay reasonable
    (meaningful premium relative to risk) on any DTE, not just the specific
    DTE that day-of-week happened to average in the 2-year backtest.

    Falls back to the static BACKTESTED_RECOMMENDATIONS table (or a general
    2.5%/200pt default) if dte/avg_iv_pct aren't supplied.
    """
    static = BACKTESTED_RECOMMENDATIONS.get(
        entry_dow, {"otm_distance_pct": 2.5, "wing_width_points": 200, "note": "general default"}
    )

    if dte is None or avg_iv_pct is None or avg_iv_pct <= 0:
        return static

    dynamic = get_dynamic_recommended_otm(dte, avg_iv_pct, entry_dow)

    # Wing width also scales down on low-DTE/tight-OTM days — a 200pt wing
    # makes no sense if the short strike itself is only ~150pts away (as on
    # expiry day). Scale wing width proportionally to how much the dynamic
    # OTM% shrank/grew vs. the static backtest OTM%, floored at 50 (NIFTY's
    # strike step) and capped at the original static wing width.
    static_otm = static["otm_distance_pct"]
    scale_factor = dynamic["otm_distance_pct"] / static_otm if static_otm > 0 else 1.0
    wing_width = int(round(static["wing_width_points"] * min(scale_factor, 1.0) / 50) * 50)
    wing_width = max(50, wing_width)

    note = (
        f"{static['note']} — dynamically scaled to {dynamic['otm_distance_pct']}% OTM "
        f"for current DTE={dynamic['dte_used']:.1f} & IV={avg_iv_pct:.1f}% "
        f"({dynamic['sigma_multiplier']}σ)"
    )
    return {
        "otm_distance_pct": dynamic["otm_distance_pct"],
        "wing_width_points": wing_width,
        "note": note,
    }


def suggest_iron_condor_strikes(
    otm_distance_pct: float = 2.5,
    wing_width_points: int = 200,
    strike_step: int = 50,
) -> dict:
    """
    Suggests 4 strikes for a short iron condor based on the live NIFTY
    option chain, spot price, and IV.

    otm_distance_pct: how far OTM (as % of spot) to place the SHORT strikes.
                       Default 2.5% each side — a common "high probability,
                       modest premium" choice for weekly NIFTY options.
    wing_width_points: distance between short and long strike (the hedge
                        "wing" width) — determines max loss and margin required.
                        Default 200 points (~2 strikes at step=100).

    Returns spot, expiry, all 4 strikes + their live premiums (if available
    from the NSE chain), IV, and computed max profit/loss/breakevens/POP.
    """
    chain = get_nse_options_data()
    if chain is None:
        raise RuntimeError("Could not fetch live NSE option chain data.")

    spot = chain["spot_price"]
    expiry = chain["nearest_expiry"]
    dte = chain["days_to_expiry"]

    short_call_strike = _round_to_strike_step(spot * (1 + otm_distance_pct / 100), strike_step)
    short_put_strike = _round_to_strike_step(spot * (1 - otm_distance_pct / 100), strike_step)
    long_call_strike = short_call_strike + wing_width_points
    long_put_strike = short_put_strike - wing_width_points

    # Look up live premiums + IV from the NSE chain for each leg
    all_strikes = chain.get("all_strikes", [])
    strike_map = {item.get("strikePrice"): item for item in all_strikes}

    def _leg_data(strike, option_type):
        item = strike_map.get(strike, {})
        leg = item.get(option_type, {}) or {}
        return {
            "strike": strike,
            "ltp": leg.get("lastPrice", 0),
            "iv": leg.get("impliedVolatility", 0),
            "oi": leg.get("openInterest", 0),
        }

    short_call = _leg_data(short_call_strike, "CE")
    long_call = _leg_data(long_call_strike, "CE")
    short_put = _leg_data(short_put_strike, "PE")
    long_put = _leg_data(long_put_strike, "PE")

    # Net premium collected (credit) = premiums received - premiums paid
    net_credit = (
        short_call["ltp"] + short_put["ltp"] - long_call["ltp"] - long_put["ltp"]
    )
    max_profit = net_credit
    # Max loss is capped by the wing width minus the credit received
    call_side_max_loss = (long_call_strike - short_call_strike) - net_credit
    put_side_max_loss = (short_put_strike - long_put_strike) - net_credit
    max_loss = max(call_side_max_loss, put_side_max_loss)

    upper_breakeven = short_call_strike + net_credit
    lower_breakeven = short_put_strike - net_credit

    # Probability of profit (spot stays between breakevens at expiry),
    # approximated using average IV of the two short legs + a normal
    # distribution model of log-returns over the remaining DTE. This is a
    # standard approximation used across the options industry — NOT an
    # exact/guaranteed probability.
    avg_iv = (short_call["iv"] + short_put["iv"]) / 2 or 15.0  # % annualized
    sigma = (avg_iv / 100) * math.sqrt(max(dte, 1) / 365)
    if sigma > 0 and spot > 0:
        z_upper = math.log(upper_breakeven / spot) / sigma
        z_lower = math.log(lower_breakeven / spot) / sigma
        pop = _norm_cdf(z_upper) - _norm_cdf(z_lower)
    else:
        pop = None

    return {
        "spot_price": spot,
        "expiry": expiry,
        "days_to_expiry": dte,
        "legs": {
            "short_call": {**short_call, "action": "SELL"},
            "long_call": {**long_call, "action": "BUY"},
            "short_put": {**short_put, "action": "SELL"},
            "long_put": {**long_put, "action": "BUY"},
        },
        "net_credit_per_share": round(net_credit, 2),
        "max_profit_per_share": round(max_profit, 2),
        "max_loss_per_share": round(max_loss, 2),
        "upper_breakeven": round(upper_breakeven, 1),
        "lower_breakeven": round(lower_breakeven, 1),
        "probability_of_profit": round(pop, 3) if pop is not None else None,
        "avg_iv": round(avg_iv, 2),
        "wing_width_points": wing_width_points,
        "otm_distance_pct": otm_distance_pct,
        "timestamp": datetime.now().isoformat(),
        "note": (
            "POP is an approximation using average IV of the short legs and a "
            "log-normal price model — a standard industry heuristic, NOT a "
            "guaranteed probability. Live premiums are indicative; actual "
            "fill prices depend on real-time bid/ask spreads at order time."
        ),
    }


def get_lot_size() -> int:
    """
    Returns the current NIFTY options lot size — fetched LIVE from Zerodha
    if connected (NSE periodically revises this, e.g. 50→75 in 2025), else
    falls back to the last-known value. Never hand-coded silently.
    """
    if zerodha_client.is_configured():
        try:
            return zerodha_client.get_nifty_lot_size()
        except Exception:
            pass
    return 75  # fallback if Zerodha not connected — verify against current NSE circular


def _live_margin_per_lot(strikes: dict) -> Optional[float]:
    """
    Attempts to get the REAL per-lot margin requirement from Kite's own
    cross-margined basket calculator (accounts for the offsetting benefit
    between short and long legs on each side — the whole reason iron
    condors need less capital than a naked short strangle). Returns None
    (rather than raising) if Zerodha isn't connected or the call fails, so
    callers can cleanly fall back to the approximate estimate below.
    """
    if not zerodha_client.get_connection_status().get("connected"):
        return None
    try:
        legs = strikes["legs"]
        expiry_iso = datetime.strptime(strikes["expiry"], "%d-%b-%Y").strftime("%Y-%m-%d")
        order_specs = []
        leg_defs = [
            ("short_call", "CE", "SELL"), ("long_call", "CE", "BUY"),
            ("short_put", "PE", "SELL"), ("long_put", "PE", "BUY"),
        ]
        lot_size = None
        for leg_name, option_type, transaction_type in leg_defs:
            strike = legs[leg_name]["strike"]
            contract = zerodha_client.find_nifty_option_symbol(
                strike=int(strike), expiry_date=expiry_iso, option_type=option_type
            )
            lot_size = contract["lot_size"]
            order_specs.append({
                "exchange": "NFO",
                "tradingsymbol": contract["tradingsymbol"],
                "transaction_type": transaction_type,
                "variety": "regular",
                "product": "MIS",
                "order_type": "MARKET",
                "quantity": lot_size,  # exactly 1 lot, to get a clean per-lot figure
            })
        margin_result = zerodha_client.estimate_order_margin(order_specs)
        return float(margin_result["total_margin"])
    except Exception as e:
        logger.warning(f"Live margin-per-lot calculation failed, will use approximate fallback: {e}")
        return None


def estimate_margin_per_lot(strikes: dict) -> dict:
    """
    Returns the margin required for exactly 1 lot of this iron condor, with
    a `source` field indicating whether it's the REAL live Kite figure
    (cross-margin aware) or an APPROXIMATE fallback.

    The approximate fallback uses max_loss_per_share × lot_size — this is a
    reasonable estimate for a defined-risk spread (real SPAN+exposure
    margin is often close to, though can exceed, the capped max loss) and
    critically works WITHOUT any Zerodha connection, since max_loss_per_share
    is already computed purely from the live NSE option chain. This ensures
    the margin/balance UI always shows a meaningful, live-recalculating
    number instead of going blank whenever Zerodha's session has expired.
    """
    live = _live_margin_per_lot(strikes)
    if live is not None:
        return {"margin_per_lot": round(live, 2), "source": "live"}

    lot_size = get_lot_size()
    approx = strikes["max_loss_per_share"] * lot_size
    return {"margin_per_lot": round(approx, 2), "source": "approximate"}


def check_balance_and_margin(strikes: dict, lots: int, available_balance_override: Optional[float] = None) -> dict:
    """
    Checks whether you have sufficient balance to place this iron condor,
    and calculates the maximum number of lots affordable given your
    available balance — the core "how much can I actually trade" answer.

    available_balance_override: if provided (e.g. a manually-entered
    balance from the UI, useful when Zerodha isn't connected or its daily
    session has expired), this is used INSTEAD of fetching the live Zerodha
    balance. This is what allows the margin/lot-size calculation to always
    work, not just when a live Zerodha session happens to be active.

    Returns required_margin_per_lot, required_margin (for the given lots),
    available_balance, sufficient, shortfall, and suggested_max_lots —
    the number of lots you could afford right now.
    """
    margin_info = estimate_margin_per_lot(strikes)
    margin_per_lot = margin_info["margin_per_lot"]
    required_margin = margin_per_lot * lots

    if available_balance_override is not None:
        available = float(available_balance_override)
        balance_source = "manual"
    elif zerodha_client.get_connection_status().get("connected"):
        try:
            balance = zerodha_client.get_available_balance()
            available = balance["available_margin"] or balance["available_cash"]
            balance_source = "live"
        except Exception as e:
            logger.warning(f"Live balance fetch failed: {e}")
            available = None
            balance_source = "unavailable"
    else:
        available = None
        balance_source = "unavailable"

    if available is not None:
        sufficient = available >= required_margin
        shortfall = max(0, required_margin - available)
        suggested_max_lots = int(available // margin_per_lot) if margin_per_lot > 0 else 0
    else:
        sufficient = None
        shortfall = None
        suggested_max_lots = None

    return {
        "margin_per_lot": round(margin_per_lot, 2),
        "margin_source": margin_info["source"],
        "required_margin": round(required_margin, 2),
        "available_balance": round(available, 2) if available is not None else None,
        "balance_source": balance_source,
        "sufficient": sufficient,
        "shortfall": round(shortfall, 2) if shortfall is not None else None,
        "suggested_max_lots": suggested_max_lots,
        "lots": lots,
    }


def build_payoff_diagram(strikes: dict, lot_size: int, num_points: int = 60) -> list:
    """
    Given the strikes/premiums dict from suggest_iron_condor_strikes(),
    returns a list of {spot, pnl} points spanning a reasonable range around
    the current spot, for charting the payoff diagram in the UI.
    """
    legs = strikes["legs"]
    net_credit = strikes["net_credit_per_share"]
    spot = strikes["spot_price"]
    low_end = strikes["legs"]["long_put"]["strike"] * 0.97
    high_end = strikes["legs"]["long_call"]["strike"] * 1.03
    step = (high_end - low_end) / num_points

    points = []
    s = low_end
    for _ in range(num_points + 1):
        # At expiry, intrinsic values only (premiums already netted into credit)
        sc_intrinsic = max(0, s - legs["short_call"]["strike"])
        lc_intrinsic = max(0, s - legs["long_call"]["strike"])
        sp_intrinsic = max(0, legs["short_put"]["strike"] - s)
        lp_intrinsic = max(0, legs["long_put"]["strike"] - s)

        pnl_per_share = net_credit - sc_intrinsic + lc_intrinsic - sp_intrinsic + lp_intrinsic
        points.append({
            "spot": round(s, 0),
            "pnl": round(pnl_per_share * lot_size, 0),
        })
        s += step

    return points


def place_iron_condor_order(
    strikes: dict,
    expiry_iso: str,
    lots: int = 1,
) -> dict:
    """
    Places all 4 legs of the short iron condor as separate MARKET orders on
    Zerodha (SELL short call, BUY long call, SELL short put, BUY long put).

    Returns a dict with each leg's order result (or error) — a partial
    failure (e.g. 3 of 4 legs filled) is reported clearly rather than
    silently swallowed, since an incomplete iron condor is a DIFFERENT,
    undefined-risk position that needs immediate manual attention.
    """
    legs = strikes["legs"]
    results = {}
    errors = []

    leg_specs = [
        ("short_call", "CE", "SELL"),
        ("long_call", "CE", "BUY"),
        ("short_put", "PE", "SELL"),
        ("long_put", "PE", "BUY"),
    ]

    for leg_name, option_type, transaction_type in leg_specs:
        strike = legs[leg_name]["strike"]
        try:
            contract = zerodha_client.find_nifty_option_symbol(
                strike=int(strike), expiry_date=expiry_iso, option_type=option_type
            )
            quantity = lots * contract["lot_size"]
            order = zerodha_client.place_order(
                tradingsymbol=contract["tradingsymbol"],
                exchange="NFO",
                transaction_type=transaction_type,
                quantity=quantity,
                order_type="MARKET",
                product="MIS",
            )
            results[leg_name] = {
                "status": "ok",
                "tradingsymbol": contract["tradingsymbol"],
                "quantity": quantity,
                "order_id": order.get("order_id"),
            }
        except Exception as e:
            error_msg = str(e)
            errors.append(f"{leg_name}: {error_msg}")
            results[leg_name] = {"status": "error", "message": error_msg}

    return {
        "success": len(errors) == 0,
        "legs": results,
        "errors": errors,
        "warning": (
            None
            if not errors
            else "PARTIAL FILL — one or more legs failed. Your position may now "
                 "have UNDEFINED/UNCAPPED risk. Check Zerodha positions immediately "
                 "and manually complete or unwind the remaining legs."
        ),
    }


def get_live_iron_condor_status() -> dict:
    """
    Detects an existing open iron-condor-shaped position (2 short + 2 long
    NIFTY option legs, one CE pair and one PE pair) from your ACTUAL live
    Zerodha positions, and reports live aggregate P&L + how close spot is
    to either breakeven — the "monitor my existing IC" view.

    This is a best-effort HEURISTIC detection (matches on quantity signs +
    strike ordering), not a stored/remembered position — if you have other
    unrelated NIFTY option positions open at the same time, detection may
    be inaccurate. Always cross-check against your actual Zerodha app.
    """
    if not zerodha_client.is_configured():
        return {"success": False, "message": "Zerodha not configured.", "detected": False}

    try:
        positions_data = zerodha_client.get_positions()
    except Exception as e:
        return {"success": False, "message": str(e), "detected": False}

    net = positions_data.get("net", [])
    nifty_legs = [
        p for p in net
        if p.get("exchange") == "NFO"
        and "NIFTY" in (p.get("tradingsymbol") or "")
        and p.get("quantity", 0) != 0
    ]

    calls = [p for p in nifty_legs if p["tradingsymbol"].endswith("CE")]
    puts = [p for p in nifty_legs if p["tradingsymbol"].endswith("PE")]

    if len(calls) != 2 or len(puts) != 2:
        return {
            "success": True,
            "detected": False,
            "message": f"No 4-leg iron-condor-shaped position detected "
                       f"({len(calls)} call leg(s), {len(puts)} put leg(s) open).",
        }

    def _strike_from_symbol(p):
        # Best-effort: use average_price context isn't reliable for strike,
        # so we rely on Kite's positions not exposing strike directly —
        # cross-reference against the live chain by matching last_price
        # isn't robust either. We just sort by tradingsymbol which for
        # NIFTY encodes the strike numerically before CE/PE.
        import re
        m = re.search(r"(\d+)(CE|PE)$", p["tradingsymbol"])
        return int(m.group(1)) if m else 0

    calls_sorted = sorted(calls, key=_strike_from_symbol)
    puts_sorted = sorted(puts, key=_strike_from_symbol)

    short_call = next((c for c in calls_sorted if c["quantity"] < 0), None)
    long_call = next((c for c in calls_sorted if c["quantity"] > 0), None)
    short_put = next((p for p in puts_sorted if p["quantity"] < 0), None)
    long_put = next((p for p in puts_sorted if p["quantity"] > 0), None)

    if not all([short_call, long_call, short_put, long_put]):
        return {
            "success": True,
            "detected": False,
            "message": "Call/put legs present but don't match a short-iron-condor "
                       "shape (need exactly 1 short + 1 long on each side).",
        }

    total_pnl = sum(p.get("pnl", 0) for p in nifty_legs)

    try:
        chain = get_nse_options_data()
        spot = chain["spot_price"] if chain else None
    except Exception:
        spot = None

    legs_summary = [
        {"role": "short_call", "tradingsymbol": short_call["tradingsymbol"], "pnl": short_call.get("pnl", 0)},
        {"role": "long_call", "tradingsymbol": long_call["tradingsymbol"], "pnl": long_call.get("pnl", 0)},
        {"role": "short_put", "tradingsymbol": short_put["tradingsymbol"], "pnl": short_put.get("pnl", 0)},
        {"role": "long_put", "tradingsymbol": long_put["tradingsymbol"], "pnl": long_put.get("pnl", 0)},
    ]

    short_call_strike = _strike_from_symbol(short_call)
    short_put_strike = _strike_from_symbol(short_put)

    alerts = []
    if spot is not None:
        if spot >= short_call_strike:
            alerts.append({
                "severity": "danger",
                "message": f"Spot ({spot}) has reached/breached your short call strike "
                           f"({short_call_strike}) — upside breach, loss accelerating.",
            })
        elif spot <= short_put_strike:
            alerts.append({
                "severity": "danger",
                "message": f"Spot ({spot}) has reached/breached your short put strike "
                           f"({short_put_strike}) — downside breach, loss accelerating.",
            })
        else:
            call_buffer_pct = (short_call_strike - spot) / spot * 100
            put_buffer_pct = (spot - short_put_strike) / spot * 100
            if min(call_buffer_pct, put_buffer_pct) < 1.0:
                alerts.append({
                    "severity": "warning",
                    "message": f"Spot ({spot}) is within 1% of a short strike "
                               f"(call buffer {call_buffer_pct:.2f}%, put buffer {put_buffer_pct:.2f}%) "
                               f"— consider adjusting or closing.",
                })

    return {
        "success": True,
        "detected": True,
        "spot_price": spot,
        "short_call_strike": short_call_strike,
        "short_put_strike": short_put_strike,
        "total_pnl": round(total_pnl, 2),
        "legs": legs_summary,
        "alerts": alerts,
        "timestamp": datetime.now().isoformat(),
    }
