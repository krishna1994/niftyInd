"""
Live Zerodha equity holdings analysis + per-holding suggestion.

Fetches your ACTUAL long-term equity holdings (portfolio.holdings — separate
from `positions`, which is today's intraday/F&O activity) and enriches each
with:
  - Live P&L (already provided by Kite, surfaced directly)
  - Technical analysis computed from real daily OHLCV data (yfinance,
    ticker = "<tradingsymbol>.NS" — same data source/indicator engine used
    elsewhere in this app for NIFTY, so it's consistent) — RSI, trend (EMA
    stack), ADX trend strength
  - A definitive BUY_MORE / HOLD / TRIM / SELL suggestion per holding,
    combining: live technical setup + your actual unrealized P&L% on that
    specific holding (not a generic threshold — your own cost basis)

This is READ-ONLY / advisory — it never places or modifies any order.
"""
import logging
from datetime import datetime

import zerodha_client
from indicators import compute_all_indicators
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

# Thresholds (surfaced in the response so the UI/user can see exactly why)
DEEP_LOSS_PCT_THRESHOLD = -15.0    # holding down >15% from your avg cost -> flagged
STRONG_GAIN_PCT_THRESHOLD = 30.0   # holding up >30% from your avg cost -> profit-booking nudge
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30


def _fetch_technicals_for_symbol(tradingsymbol: str) -> dict:
    """
    Fetches ~6 months of daily OHLCV for this NSE-listed stock via yfinance
    and computes the same indicator set used elsewhere in this app, so
    holdings suggestions are built on the SAME technical analysis engine
    (RSI, EMA trend stack, ADX) rather than a separate, inconsistent one.

    Returns None (rather than raising) if data can't be fetched — e.g. an
    unusual/delisted symbol yfinance doesn't recognize — so one bad symbol
    never breaks the whole holdings list.
    """
    yf_ticker = f"{tradingsymbol}.NS"
    try:
        df = yf.download(yf_ticker, period="6mo", interval="1d", progress=False)
        if df is None or df.empty or len(df) < 30:
            return None

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).strip() for c in df.columns]
        ohlcv_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        df = df[ohlcv_cols]

        df = compute_all_indicators(df)
        latest = df.iloc[-1]

        rsi = float(latest["RSI"]) if pd.notna(latest["RSI"]) else None
        adx = float(latest["ADX"]) if pd.notna(latest["ADX"]) else None
        ema9 = float(latest["EMA9"]) if pd.notna(latest["EMA9"]) else None
        ema21 = float(latest["EMA21"]) if pd.notna(latest["EMA21"]) else None
        ema50 = float(latest["EMA50"]) if pd.notna(latest["EMA50"]) else None
        ema200 = float(latest["EMA200"]) if pd.notna(latest["EMA200"]) else None
        close = float(latest["Close"]) if pd.notna(latest["Close"]) else None

        # Trend classification from the EMA stack (standard "stacked EMA" heuristic)
        trend = "NEUTRAL"
        if all(v is not None for v in (ema9, ema21, ema50)):
            if ema9 > ema21 > ema50:
                trend = "UPTREND"
            elif ema9 < ema21 < ema50:
                trend = "DOWNTREND"

        above_200ema = (close is not None and ema200 is not None and close > ema200)

        return {
            "rsi": round(rsi, 1) if rsi is not None else None,
            "adx": round(adx, 1) if adx is not None else None,
            "trend": trend,
            "above_200ema": above_200ema,
            "close": round(close, 2) if close is not None else None,
        }
    except Exception as e:
        logger.warning(f"holdings_analysis: could not fetch technicals for {tradingsymbol}: {e}")
        return None


def _suggestion_for_holding(pnl_pct: float, technicals: dict) -> dict:
    """
    Combines your ACTUAL unrealized P&L% on this specific holding with its
    live technical setup to produce a definitive BUY_MORE / HOLD / TRIM /
    SELL recommendation + the specific reasons.
    """
    reasons = []
    recommendation = "HOLD"

    rsi = technicals.get("rsi") if technicals else None
    trend = technicals.get("trend") if technicals else None
    above_200ema = technicals.get("above_200ema") if technicals else None
    adx = technicals.get("adx") if technicals else None

    # 1) Deep loss on this specific holding — real cost-basis based, not generic
    if pnl_pct <= DEEP_LOSS_PCT_THRESHOLD:
        reasons.append({
            "type": "DEEP_LOSS",
            "message": f"Down {pnl_pct:.1f}% from your average cost.",
        })
        recommendation = "SELL" if (trend == "DOWNTREND" and above_200ema is False) else "TRIM"

    # 2) Strong technical downtrend + below 200 EMA — bearish setup regardless of P&L
    if trend == "DOWNTREND" and above_200ema is False:
        reasons.append({
            "type": "BEARISH_TECHNICAL",
            "message": "Price is below the 200-day average and in a confirmed downtrend (EMA9<EMA21<EMA50).",
        })
        if recommendation == "HOLD":
            recommendation = "TRIM"

    # 3) Overbought RSI while already up a lot — profit-booking nudge
    if pnl_pct >= STRONG_GAIN_PCT_THRESHOLD and rsi is not None and rsi >= RSI_OVERBOUGHT:
        reasons.append({
            "type": "OVERBOUGHT_PROFIT",
            "message": f"Up {pnl_pct:.1f}% from cost AND RSI is overbought ({rsi}) — consider booking some profit.",
        })
        recommendation = "TRIM"

    # 4) Strong uptrend + oversold-ish RSI (pullback in an uptrend) — accumulation opportunity
    if trend == "UPTREND" and above_200ema and rsi is not None and rsi <= 45 and pnl_pct > -5:
        reasons.append({
            "type": "PULLBACK_IN_UPTREND",
            "message": f"Confirmed uptrend, price above 200-day average, RSI has pulled back to {rsi} — potential add-on opportunity.",
        })
        if recommendation == "HOLD":
            recommendation = "BUY_MORE"

    # 5) Strong trend confirmation (high ADX) reinforces whatever direction it's already in
    if adx is not None and adx >= 25:
        if trend == "UPTREND":
            reasons.append({"type": "STRONG_TREND", "message": f"Strong confirmed uptrend (ADX {adx})."})
        elif trend == "DOWNTREND":
            reasons.append({"type": "STRONG_TREND", "message": f"Strong confirmed downtrend (ADX {adx})."})

    if not reasons:
        reasons.append({"type": "NEUTRAL", "message": "No strong signal either way — technicals and P&L are in a normal range."})

    return {"recommendation": recommendation, "reasons": reasons}


def get_live_holdings_with_analysis() -> dict:
    """
    Returns all Zerodha equity holdings enriched with live P&L, technical
    analysis, and a per-holding BUY_MORE/HOLD/TRIM/SELL suggestion.

    Returns {"success": bool, "holdings": [...], "portfolio_summary": {...}}.
    On any error (Zerodha not connected, etc.) returns success=False with a
    clear message — never raises.
    """
    if not zerodha_client.is_configured():
        return {
            "success": False,
            "message": "Zerodha not configured — no holdings to show.",
            "holdings": [],
        }

    try:
        holdings = zerodha_client.get_holdings()
    except RuntimeError as e:
        return {"success": False, "message": str(e), "holdings": []}
    except Exception as e:
        logger.error(f"holdings_analysis: failed to fetch holdings: {e}")
        return {"success": False, "message": f"Could not fetch holdings: {e}", "holdings": []}

    if not holdings:
        return {
            "success": True,
            "message": "No equity holdings found in your Zerodha account.",
            "holdings": [],
            "portfolio_summary": {"total_invested": 0, "total_current_value": 0, "total_pnl": 0, "total_pnl_pct": 0},
        }

    enriched = []
    total_invested = 0.0
    total_current_value = 0.0

    for h in holdings:
        tradingsymbol = h.get("tradingsymbol", "")
        quantity = h.get("quantity", 0)
        avg_price = h.get("average_price", 0)
        last_price = h.get("last_price", 0)
        pnl = h.get("pnl", 0)
        day_change_pct = h.get("day_change_percentage", 0)

        invested_value = avg_price * quantity
        current_value = last_price * quantity
        pnl_pct = (pnl / invested_value * 100) if invested_value > 0 else 0.0

        total_invested += invested_value
        total_current_value += current_value

        technicals = _fetch_technicals_for_symbol(tradingsymbol)
        suggestion = _suggestion_for_holding(pnl_pct, technicals)

        enriched.append({
            "tradingsymbol": tradingsymbol,
            "exchange": h.get("exchange"),
            "quantity": quantity,
            "average_price": avg_price,
            "last_price": last_price,
            "invested_value": round(invested_value, 2),
            "current_value": round(current_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "day_change_pct": round(day_change_pct, 2) if day_change_pct is not None else None,
            "technicals": technicals,
            "recommendation": suggestion["recommendation"],
            "reasons": suggestion["reasons"],
        })

    total_pnl = total_current_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0.0

    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "holdings": enriched,
        "holding_count": len(enriched),
        "portfolio_summary": {
            "total_invested": round(total_invested, 2),
            "total_current_value": round(total_current_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
        },
    }