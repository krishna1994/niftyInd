"""
Global Stocks/ETF Watchlist — live tracker + signal for a fixed set of
non-Indian stocks/ETFs the user wants to swing-trade / long-term hold
(Qualcomm, Google, Meta, Gold, Silver, TSMC, Nvidia, Micron, Samsung,
Microsoft, Nasdaq-100).

DESIGN — reuses existing, already-generic modules rather than duplicating
logic:
  - `indicators.compute_all_indicators()` operates on any standard OHLCV
    DataFrame (RSI/MACD/EMA/ADX/Supertrend/etc. are generic technical math,
    nothing NIFTY-specific about them).
  - `signal_engine.generate_signal()` is also generic — it only needs an
    OHLCV DataFrame + a VIX-like volatility number. Since India VIX doesn't
    apply to these tickers, we pass a neutral value (15.0, i.e. "calm
    market") so the VIX confidence-penalty logic simply never fires — this
    is an explicit, documented choice, not a silent hack.

WHAT'S NEW HERE (not duplicated from elsewhere):
  - Long-term trend context: price vs 200-day EMA, 52-week high/low
    distance, 1-year return — none of which signal_engine.py computes,
    since it's built for weekly-options swing trading, not long-term
    positioning.
  - A combined recommendation that reconciles the SHORT-TERM swing signal
    with the LONG-TERM trend (e.g. "short-term weak dip within a still-
    bullish long-term trend" reads very differently from "both bearish").
  - Suggested stop-loss/target PRICE levels (not option strikes) sized
    off each stock's own ATR.

CACHING: results cached for CACHE_SECONDS (default 5 min) — this is a
swing/long-term watchlist, not a fast-moving intraday signal, so aggressive
polling would be wasteful and risks yfinance rate-limiting across 11
tickers. Tickers are fetched SEQUENTIALLY (not in parallel) — confirmed via
direct testing that concurrent yf.download() calls across threads
cross-contaminate results between different tickers (a real yfinance
correctness issue, not a bug in this code). The ~10-15s total fetch time
this adds only happens once per 5-minute cache window, not per request.
"""
import logging
import threading
import time

import pandas as pd
import requests
import yfinance as yf

from indicators import compute_all_indicators
from signal_engine import generate_signal
from database import get_custom_watchlist_symbols

logger = logging.getLogger(__name__)

# ticker -> display name. Samsung has no primary US-listed common share;
# 005930.KS (Korea Exchange) is used as it returns clean, reliable daily
# OHLCV via yfinance (the OTC ADR SSNLF is much thinner/less reliable).
WATCHLIST = {
    "QCOM": "Qualcomm",
    "GOOGL": "Alphabet (Google)",
    "META": "Meta Platforms",
    "GLD": "Gold (SPDR Gold Shares ETF)",
    "SLV": "Silver (iShares Silver Trust ETF)",
    "TSM": "Taiwan Semiconductor (TSMC)",
    "NVDA": "Nvidia",
    "MU": "Micron Technology",
    "005930.KS": "Samsung Electronics",
    "MSFT": "Microsoft",
    "QQQ": "Nasdaq-100 (Invesco QQQ ETF)",
}

# Neutral "calm market" VIX value — passed to generate_signal() purely to
# satisfy its required parameter; India VIX has no relevance to these
# tickers, so this deliberately keeps the VIX confidence-penalty inert
# (penalty only starts above 20).
_NEUTRAL_VIX = 15.0

CACHE_SECONDS = 300  # 5 minutes — see module docstring for rationale

_cache_lock = threading.Lock()
_cache = {"result": None, "timestamp": 0}


def _fetch_ohlcv(ticker: str, period: str = "1y", interval: str = "1d"):
    """Fetch + normalize OHLCV data for any yfinance ticker (index/stock/ETF)."""
    df = yf.download(ticker, period=period, interval=interval, progress=False)
    if df is None or df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).strip() for c in df.columns]
    ohlcv_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[ohlcv_cols].dropna(subset=["Close"])
    return df


def analyze_symbol(ticker: str, name: str) -> dict:
    """
    Full analysis for one symbol: live price, generic technical signal
    (reusing signal_engine.py), long-term trend context, and a combined
    swing-trade recommendation with suggested stop-loss/target.
    Never raises — returns {"success": False, "error": ...} on any failure
    so one bad/delisted ticker never breaks the whole watchlist.
    """
    try:
        df = _fetch_ohlcv(ticker, period="1y", interval="1d")
        if df is None or len(df) < 30:
            return {"symbol": ticker, "name": name, "success": False,
                     "error": "Insufficient live data returned from yfinance"}

        df = compute_all_indicators(df)
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest

        spot = float(latest["Close"])
        prev_close = float(prev["Close"])
        day_change_pct = ((spot - prev_close) / prev_close) * 100 if prev_close else 0.0

        # Generic short-term swing signal — same engine used for NIFTY,
        # working purely off this stock's own OHLCV + indicators.
        signal_result = generate_signal(df, vix=_NEUTRAL_VIX)

        # ── Long-term trend context (new — not in signal_engine.py) ──────
        ema200 = float(latest["EMA200"]) if not pd.isna(latest["EMA200"]) else None
        above_200ema = (spot > ema200) if ema200 else None
        pct_from_200ema = ((spot - ema200) / ema200 * 100) if ema200 else None
        long_term_trend = "BULLISH" if above_200ema else ("BEARISH" if above_200ema is False else "UNKNOWN")

        lookback = min(len(df), 252)
        high_52w = float(df["High"].tail(lookback).max())
        low_52w = float(df["Low"].tail(lookback).min())
        pct_from_52w_high = ((spot - high_52w) / high_52w) * 100
        pct_from_52w_low = ((spot - low_52w) / low_52w) * 100

        # ~1-year return, using whatever the earliest available close is if
        # a full 252-trading-day year isn't available (yfinance's "1y"
        # period sometimes returns 250-251 rows depending on holidays) —
        # close enough to be a meaningful "roughly 1 year" reference point
        # rather than showing nothing at all.
        one_year_return_pct = None
        if len(df) >= 200:
            year_ago_idx = max(0, len(df) - 252)
            year_ago_close = float(df["Close"].iloc[year_ago_idx])
            if year_ago_close:
                one_year_return_pct = ((spot - year_ago_close) / year_ago_close) * 100

        # ── Swing action translated from NIFTY-style labels to stock terms ──
        swing_signal = signal_result["signal"]  # BUY CE / BUY PE / STAY OUT
        if swing_signal == "BUY CE":
            swing_action = "BUY"
        elif swing_signal == "BUY PE":
            swing_action = "SELL/AVOID"
        else:
            swing_action = "HOLD/WAIT"

        # ── Combined recommendation: reconcile short-term vs long-term ──────
        if swing_action == "BUY" and long_term_trend == "BULLISH":
            recommendation = "STRONG BUY"
            recommendation_reason = "Short-term swing signal AND long-term trend (above 200-day EMA) both bullish."
        elif swing_action == "BUY" and long_term_trend == "BEARISH":
            recommendation = "BUY (counter-trend — caution)"
            recommendation_reason = "Short-term signal is bullish, but the stock is below its 200-day EMA (long-term downtrend) — consider smaller size and a tighter stop."
        elif swing_action == "SELL/AVOID" and long_term_trend == "BEARISH":
            recommendation = "AVOID / TRIM"
            recommendation_reason = "Short-term swing signal AND long-term trend both bearish."
        elif swing_action == "SELL/AVOID" and long_term_trend == "BULLISH":
            recommendation = "HOLD (pullback in uptrend)"
            recommendation_reason = "Short-term weakness while still above the 200-day EMA — often just a pullback within an intact uptrend, not necessarily a reason to exit a long-term position."
        elif long_term_trend == "BULLISH":
            recommendation = "HOLD / ACCUMULATE ON DIPS"
            recommendation_reason = "No strong short-term edge right now, but the long-term trend (above 200-day EMA) remains intact."
        elif long_term_trend == "BEARISH":
            recommendation = "HOLD / WAIT FOR TREND REVERSAL"
            recommendation_reason = "No strong short-term edge, and the long-term trend (below 200-day EMA) is unfavorable — wait for a clearer setup."
        else:
            recommendation = "HOLD/WATCH"
            recommendation_reason = "Not enough data yet to establish a long-term trend reliably; no strong short-term edge either."

        atr = float(latest["ATR"]) if not pd.isna(latest["ATR"]) else spot * 0.02
        if swing_action == "BUY":
            suggested_stop_loss = spot - 1.5 * atr
            suggested_target = spot + 2.5 * atr
        elif swing_action == "SELL/AVOID":
            suggested_stop_loss = spot + 1.5 * atr
            suggested_target = spot - 2.5 * atr
        else:
            suggested_stop_loss = None
            suggested_target = None

        ind = signal_result["indicators"]

        return {
            "symbol": ticker,
            "name": name,
            "success": True,
            "spot": round(spot, 2),
            "day_change_pct": round(day_change_pct, 2),
            "swing_signal": swing_signal,
            "swing_action": swing_action,
            "bull_confidence": round(signal_result["bull_confidence"], 1),
            "bear_confidence": round(signal_result["bear_confidence"], 1),
            "long_term_trend": long_term_trend,
            "pct_from_200ema": round(pct_from_200ema, 2) if pct_from_200ema is not None else None,
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "pct_from_52w_high": round(pct_from_52w_high, 2),
            "pct_from_52w_low": round(pct_from_52w_low, 2),
            "one_year_return_pct": round(one_year_return_pct, 2) if one_year_return_pct is not None else None,
            "recommendation": recommendation,
            "recommendation_reason": recommendation_reason,
            "suggested_stop_loss": round(suggested_stop_loss, 2) if suggested_stop_loss is not None else None,
            "suggested_target": round(suggested_target, 2) if suggested_target is not None else None,
            "rsi": round(float(latest["RSI"]), 1) if not pd.isna(latest["RSI"]) else None,
            "adx": round(float(latest["ADX"]), 1) if not pd.isna(latest["ADX"]) else None,
            "macd_label": ind["macd"]["label"],
            "supertrend_label": ind["supertrend"]["label"],
            "candle_pattern": ind["candle_pattern"]["pattern"],
        }

    except Exception as e:
        logger.error(f"watchlist_analysis: error analyzing {ticker}: {e}")
        return {"symbol": ticker, "name": name, "success": False, "error": str(e)}


def lookup_symbol_name(ticker: str):
    """
    Best-effort human-readable name lookup for a ticker via yfinance's
    quote metadata (e.g. "AAPL" -> "Apple Inc."). Returns None if the
    lookup fails or the ticker doesn't exist — callers should fall back to
    the raw ticker symbol as the display name in that case.
    """
    try:
        info = yf.Ticker(ticker).info
        if not info or not info.get("quoteType"):
            return None
        return info.get("shortName") or info.get("longName") or None
    except Exception as e:
        logger.warning(f"watchlist_analysis: name lookup failed for {ticker}: {e}")
        return None


# Auto-tried suffixes when a bare symbol (no exchange suffix at all) fails
# to resolve — this app is NIFTY-focused, so most users naturally type a
# bare Indian ticker like "RELIANCE" or "TCS" expecting it to just work,
# rather than knowing yfinance requires an explicit ".NS"/".BO" suffix.
# NSE is tried first (it's the far more liquid of the two for virtually
# every dual-listed Indian stock).
_INDIAN_SUFFIX_FALLBACKS = [".NS", ".BO"]


def validate_symbol(ticker: str) -> dict:
    """
    Checks whether a user-searched ticker is a real, fetchable symbol
    before it's added to the custom watchlist — avoids silently adding a
    typo'd ticker that will just show as a permanent error card. Returns
    {"valid": bool, "name": str|None, "error": str|None, "resolved_symbol": str}.

    Supports NSE/BSE Indian stocks: if a BARE symbol (no "." in it at all,
    e.g. "RELIANCE", "TCS", "INFY") doesn't resolve directly, automatically
    retries with ".NS" (NSE) then ".BO" (BSE) appended, and returns the
    actual resolved symbol (e.g. "RELIANCE.NS") so the frontend adds the
    correct, unambiguous ticker rather than the bare one.
    """
    ticker = ticker.strip().upper()
    if not ticker:
        return {"valid": False, "name": None, "error": "Empty symbol", "resolved_symbol": None}

    candidates = [ticker]
    if "." not in ticker:
        candidates += [ticker + suffix for suffix in _INDIAN_SUFFIX_FALLBACKS]

    last_error = None
    for candidate in candidates:
        try:
            df = _fetch_ohlcv(candidate, period="5d", interval="1d")
            if df is not None and not df.empty:
                name = lookup_symbol_name(candidate) or candidate
                return {"valid": True, "name": name, "error": None, "resolved_symbol": candidate}
        except Exception as e:
            last_error = str(e)

    return {
        "valid": False,
        "name": None,
        "error": last_error or f"No data found for '{ticker}' — for Indian stocks try RELIANCE.NS (NSE) or RELIANCE.BO (BSE); for other exchanges try e.g. 7203.T (Tokyo)",
        "resolved_symbol": None,
    }


_YAHOO_SEARCH_URL = "https://query1.finance.yahoo.com/v1/finance/search"
_YAHOO_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def search_suggestions(query: str, limit: int = 8) -> list:
    """
    Live autocomplete suggestions as the user types a symbol/company name,
    using Yahoo Finance's public (unauthenticated) search endpoint — the
    SAME data source yfinance itself sits on top of, so anything returned
    here is guaranteed to also work with validate_symbol()/analyze_symbol().

    Returns a list of {"symbol", "name", "exchange", "type"} dicts, ranked
    by Yahoo's own relevance score (already filtered to EQUITY/ETF/INDEX
    quote types — mutual funds/options/etc. excluded since they don't make
    sense in this swing-trading watchlist). Best-effort: returns an empty
    list (never raises) if the query is too short or the request fails,
    so a flaky external search never breaks the Add flow — the user can
    always still type a full exact symbol themselves.
    """
    query = (query or "").strip()
    if len(query) < 2:
        return []
    try:
        resp = requests.get(
            _YAHOO_SEARCH_URL,
            params={"q": query, "quotesCount": limit, "newsCount": 0},
            headers=_YAHOO_HEADERS,
            timeout=4,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        quotes = data.get("quotes", [])
        suggestions = []
        for q in quotes:
            quote_type = q.get("quoteType")
            if quote_type not in ("EQUITY", "ETF", "INDEX"):
                continue
            symbol = q.get("symbol")
            if not symbol:
                continue
            suggestions.append({
                "symbol": symbol,
                "name": q.get("shortname") or q.get("longname") or symbol,
                "exchange": q.get("exchDisp") or q.get("exchange") or "",
                "type": quote_type,
            })
        return suggestions[:limit]
    except Exception as e:
        logger.warning(f"watchlist_analysis: search_suggestions failed for '{query}': {e}")
        return []


def _get_full_watchlist_dict() -> dict:
    """Built-in WATCHLIST merged with any user-added custom symbols
    (custom symbols never overwrite a built-in entry with the same ticker,
    and are appended in the order they were added). Returns
    {ticker: {"name": ..., "is_custom": bool}}."""
    full = {t: {"name": n, "is_custom": False} for t, n in WATCHLIST.items()}
    for row in get_custom_watchlist_symbols():
        symbol = row["symbol"]
        if symbol not in full:
            full[symbol] = {"name": row.get("name") or symbol, "is_custom": True}
    return full


def _compute_watchlist_analysis() -> dict:
    """
    Fetches + analyzes every ticker (built-in WATCHLIST + any user-added
    custom symbols) SEQUENTIALLY.

    IMPORTANT — this was originally parallelized via ThreadPoolExecutor,
    but direct testing revealed yfinance's `yf.download()` is NOT safe to
    call concurrently across threads for DIFFERENT tickers: multiple
    tickers' results got cross-contaminated (several unrelated tickers
    all returned the SAME price data). This is a genuine correctness bug
    in yfinance's shared/global session handling under concurrency, not a
    threading mistake in this code — confirmed by testing that sequential
    calls to the exact same function are 100% correct. Sequential fetching
    is slower (~1-2s per ticker) but is CORRECT, and this result is cached
    for 5 minutes anyway (see CACHE_SECONDS), so the extra latency is a
    one-time cost per cache window, not per request.
    """
    full_watchlist = _get_full_watchlist_dict()
    results = []
    for ticker, meta in full_watchlist.items():
        r = analyze_symbol(ticker, meta["name"])
        r["is_custom"] = meta["is_custom"]
        results.append(r)

    success_count = sum(1 for r in results if r.get("success"))
    return {
        "success": True,
        "watchlist": results,
        "count": len(results),
        "success_count": success_count,
        "timestamp": pd.Timestamp.now().isoformat(),
    }


def get_cached_watchlist_analysis(force_refresh: bool = False) -> dict:
    """
    Main entry point — returns the cached result if fresh (<CACHE_SECONDS
    old), otherwise recomputes. Thread-safe.
    """
    now = time.time()
    with _cache_lock:
        cached = _cache["result"]
        if cached is not None and not force_refresh and (now - _cache["timestamp"]) < CACHE_SECONDS:
            return {**cached, "cached": True}

    result = _compute_watchlist_analysis()
    with _cache_lock:
        _cache["result"] = result
        _cache["timestamp"] = now
    return {**result, "cached": False}