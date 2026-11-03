"""
eToro Portfolio Tracker — MANUAL entry, live analysis.

WHY MANUAL, NOT A LIVE API SYNC:
Confirmed via direct testing that eToro does NOT offer a self-serve public
API for retail accounts, unlike Zerodha (Kite Connect):
  - No maintained Python client exists for it (checked PyPI directly).
  - Their web endpoints return 401/403 without partner-level credentials —
    one endpoint (/api/public/v1/instruments) does exist and returns 401
    (meaning an API is real), but it's only issued to approved
    institutional/data-vendor partners, not to individual traders who sign
    up for a normal personal eToro account.
  - eToro's own developer/API docs make no mention of a retail self-serve
    API key flow (unlike Zerodha's public developer console).
So this module instead lets the user manually record what they hold on
eToro (symbol, quantity, entry price) and applies the SAME live technical
analysis engine used elsewhere in this app to generate real P&L + a
BUY_MORE/HOLD/TRIM/SELL suggestion — reusing indicators.py/signal_engine.py
exactly like watchlist_analysis.py and holdings_analysis.py do.

If eToro ever grants partner API access to this account, this module's
`analyze_holding()` function can be reused as-is — only the DB-backed
"holdings list" source (currently `database.get_etoro_holdings()`) would
need to be swapped for a live API call.
"""
import logging

import pandas as pd
import yfinance as yf

from indicators import compute_all_indicators
from signal_engine import generate_signal
from database import get_etoro_holdings

logger = logging.getLogger(__name__)

# Same neutral VIX rationale as watchlist_analysis.py — these are non-Indian
# (or at least non-NIFTY-options) instruments, so the India-VIX-based
# confidence penalty in generate_signal() is irrelevant and kept inert.
_NEUTRAL_VIX = 15.0


def _fetch_ohlcv(ticker: str, period: str = "1y", interval: str = "1d"):
    """Fetch + normalize OHLCV data for any yfinance ticker."""
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).strip() for c in df.columns]
    ohlcv_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[ohlcv_cols].dropna(subset=["Close"])
    return df


def analyze_holding(holding: dict) -> dict:
    """
    Analyzes one manually-entered eToro holding: live price, P&L based on
    the user's OWN entry price/quantity, the same technical signal engine
    used across this app, and a combined BUY_MORE/HOLD/TRIM/SELL suggestion
    that factors in the user's actual unrealized P&L% (not just a generic
    technical read) — same pattern as holdings_analysis.py for Zerodha.

    Never raises — returns {"success": False, "error": ...} on failure so
    one bad symbol never breaks the rest of the portfolio view.
    """
    symbol = holding["symbol"]
    try:
        df = _fetch_ohlcv(symbol, period="1y", interval="1d")
        if df is None or len(df) < 30:
            return {
                "id": holding["id"], "symbol": symbol, "name": holding.get("name") or symbol,
                "quantity": holding["quantity"], "entry_price": holding["entry_price"],
                "success": False, "error": "Insufficient live data returned from yfinance",
            }

        df = compute_all_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        spot = float(latest["Close"])
        prev_close = float(prev["Close"])
        day_change_pct = ((spot - prev_close) / prev_close) * 100 if prev_close else 0.0

        quantity = float(holding["quantity"])
        entry_price = float(holding["entry_price"])
        invested = quantity * entry_price
        current_value = quantity * spot
        pnl = current_value - invested
        pnl_pct = ((spot - entry_price) / entry_price) * 100 if entry_price else 0.0

        signal_result = generate_signal(df, vix=_NEUTRAL_VIX)
        swing_signal = signal_result["signal"]  # BUY CE / BUY PE / STAY OUT
        if swing_signal == "BUY CE":
            swing_action = "BUY"
        elif swing_signal == "BUY PE":
            swing_action = "SELL/AVOID"
        else:
            swing_action = "HOLD/WAIT"

        ema200 = float(latest["EMA200"]) if not pd.isna(latest["EMA200"]) else None
        long_term_trend = "UNKNOWN"
        if ema200:
            long_term_trend = "BULLISH" if spot > ema200 else "BEARISH"

        rsi = float(latest["RSI"]) if not pd.isna(latest["RSI"]) else None

        # ── Combined suggestion: technical setup + ACTUAL cost-basis P&L ──
        # Same philosophy as holdings_analysis.py: a generic technical read
        # alone isn't the full picture — a deep loss combined with a
        # bearish setup is a much stronger SELL signal than either alone,
        # and a strong unrealized gain combined with overbought RSI is a
        # much stronger TRIM signal than a generic technical read alone.
        reasons = []
        if pnl_pct <= -15 and swing_action == "SELL/AVOID":
            recommendation = "SELL"
            reasons.append(f"Down {pnl_pct:.1f}% from your entry AND the short-term technical signal is bearish.")
        elif pnl_pct <= -15:
            recommendation = "HOLD (review stop-loss)"
            reasons.append(f"Down {pnl_pct:.1f}% from your entry — consider a hard stop-loss if this deepens, even though the technical signal isn't outright bearish.")
        elif pnl_pct >= 30 and rsi is not None and rsi >= 70:
            recommendation = "TRIM"
            reasons.append(f"Up {pnl_pct:.1f}% from your entry and RSI is overbought ({rsi:.0f}) — consider booking some profit.")
        elif swing_action == "BUY" and long_term_trend == "BULLISH":
            recommendation = "BUY MORE"
            reasons.append("Short-term technical signal AND long-term trend (above 200-day EMA) both bullish.")
        elif swing_action == "SELL/AVOID" and long_term_trend == "BEARISH":
            recommendation = "TRIM / REDUCE"
            reasons.append("Short-term technical signal AND long-term trend both bearish.")
        else:
            recommendation = "HOLD"
            reasons.append("No strong combined signal from your P&L and the current technical setup right now.")

        ind = signal_result["indicators"]
        reasons.append(f"MACD: {ind['macd']['label']}")
        reasons.append(f"Supertrend: {ind['supertrend']['label']}")

        return {
            "id": holding["id"],
            "symbol": symbol,
            "name": holding.get("name") or symbol,
            "success": True,
            "quantity": quantity,
            "entry_price": round(entry_price, 4),
            "spot": round(spot, 4),
            "day_change_pct": round(day_change_pct, 2),
            "invested": round(invested, 2),
            "current_value": round(current_value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "swing_action": swing_action,
            "long_term_trend": long_term_trend,
            "rsi": round(rsi, 1) if rsi is not None else None,
            "recommendation": recommendation,
            "reasons": reasons,
            "notes": holding.get("notes") or "",
        }

    except Exception as e:
        logger.error(f"etoro_analysis: error analyzing {symbol}: {e}")
        return {
            "id": holding["id"], "symbol": symbol, "name": holding.get("name") or symbol,
            "quantity": holding.get("quantity"), "entry_price": holding.get("entry_price"),
            "success": False, "error": str(e),
        }


def get_portfolio_with_analysis() -> dict:
    """
    Fetches every manually-entered eToro holding and runs analyze_holding()
    on each SEQUENTIALLY (same yfinance-concurrency-safety rationale as
    watchlist_analysis.py — concurrent yf.download() calls for different
    tickers have been directly confirmed to cross-contaminate results).
    Returns the full portfolio + an aggregate summary.
    """
    holdings = get_etoro_holdings()
    results = [analyze_holding(h) for h in holdings]

    successful = [r for r in results if r.get("success")]
    total_invested = sum(r["invested"] for r in successful)
    total_current_value = sum(r["current_value"] for r in successful)
    total_pnl = total_current_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0.0

    return {
        "success": True,
        "holdings": results,
        "holding_count": len(results),
        "success_count": len(successful),
        "portfolio_summary": {
            "total_invested": round(total_invested, 2),
            "total_current_value": round(total_current_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
        },
    }