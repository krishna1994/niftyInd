"""
FastAPI backend for Nifty Weekly Option Signal Analyzer
Fetches real market data via yfinance, computes indicators, generates signals
"""
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from typing import List
import logging
import numpy as np

# Load environment variables from backend/.env (if present) BEFORE any
# module that reads os.environ at import time (e.g. zerodha_client.py).
# Safe no-op if the file doesn't exist — the app works fine without it.
from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from data import fetch_nifty, fetch_vix
from indicators import compute_all_indicators
from signal_engine import generate_signal, suggest_strikes
from backtester import run_backtest, get_dte, get_next_expiry
from nse_options import get_nse_options_data
from database import (
    init_db,
    get_cached_backtest, save_backtest_cache, clear_backtest_cache,
    create_dry_run_trade, get_dry_run_trades, close_dry_run_trade,
    delete_dry_run_trade, clear_dry_run_trades,
    log_signal, get_signal_history,
    get_auto_trade_log,
)
import cas_service
import zerodha_client
import dataset_updater
import auto_trader
import position_risk
import iron_condor
import zerodha_autologin
import holdings_analysis
import watchlist_analysis
import etoro_analysis
from volatility_analytics import get_enhanced_volatility_analysis, VolatilityAnalytics
from broker_manager import broker_manager
from strategy_builder import StrategyTemplates, OptionStrategy, OptionLeg

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialise SQLite database on startup
init_db()

app = FastAPI(title="Nifty Signal Analyzer API")

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _warm_start_cas_models():
    """
    Pre-train the CAS signal models once at server startup (in a background
    thread so it doesn't block the server from accepting requests), so the
    FIRST user request to /api/cas-signal is fast instead of paying the
    one-time model-training cost.
    """
    import threading
    threading.Thread(target=cas_service.warm_start, daemon=True).start()


@app.on_event("startup")
def _start_dataset_auto_updater():
    """
    Start the background thread that periodically checks for newly-completed
    trading days and appends them to master_dataset.csv / master_dataset_v2.csv
    (see dataset_updater.py). This is what makes the CAS models genuinely
    LEARN from new live market data over time, rather than being frozen on
    whatever historical snapshot existed when the dataset files were last
    manually built.
    """
    dataset_updater.start_background_updater()


@app.on_event("startup")
def _start_zerodha_auto_reconnect():
    """
    Starts the background loop that auto-refreshes the Zerodha session using
    remembered credentials (if any were saved via /api/zerodha/auto-login).
    Fully inert if no credentials are remembered.
    """
    zerodha_client.start_auto_reconnect_background_loop()


@app.on_event("startup")
def _start_auto_trader():
    """
    Start the auto-trader's background monitoring loop (see auto_trader.py).
    IMPORTANT: this does NOT mean auto-trading is active — the loop itself
    checks an explicit enabled/disabled setting (defaulting to OFF, and
    forced OFF on every server restart for safety) before ever placing a
    real order. Starting the loop just means it's WATCHING; it stays
    completely inert unless a human explicitly turns it on via Settings.
    """
    auto_trader.start_background_loop()


# ── Global Portfolio & Broker Management ──────────────────────────────────────

@app.get("/api/global-portfolio")
def get_global_portfolio():
    """
    The 'Command Center' endpoint. Aggregates all positions from Zerodha, 
    IBKR, and eToro into a single unified view.
    """
    try:
        return broker_manager.get_aggregated_portfolio()
    except Exception as e:
        logger.error(f"Error fetching global portfolio: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/brokers/status")
def get_brokers_status():
    """Returns connection status for all integrated brokers."""
    return broker_manager.get_all_statuses()

@app.post("/api/brokers/order")
def place_broker_order(broker_name: str, order_details: dict):
    """Routes an order to a specific broker (Zerodha or IBKR)."""
    try:
        return broker_manager.route_order(broker_name, order_details)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ── Root ───────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"app": "Nifty Signal Analyzer API", "docs": "/docs", "health": "/api/health"}


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "data_source": "yfinance",
        "timestamp": datetime.now().isoformat()
    }


# ── Signal ─────────────────────────────────────────────────────────────────────

@app.get("/api/signal")
def get_signal(
    interval: str = Query("1d", description="Interval: 1d, 1h, 15m"),
    period: str = Query("6mo", description="Period: 6mo, 3mo, 1y")
):
    """
    Get current Nifty signal with all indicator values.
    Also logs the signal to the database.
    """
    try:
        df = fetch_nifty(period, interval)
        vix = fetch_vix()
        df = compute_all_indicators(df)
        signal_result = generate_signal(df, vix)
        strikes = suggest_strikes(signal_result, df.iloc[-1])

        if vix > 28:
            vix_regime = "EXTREME"; vix_penalty = 20
            vix_message = f"VIX at {vix:.2f} — extreme fear, signals blocked (-20% confidence)"
        elif vix > 22:
            vix_regime = "HIGH"; vix_penalty = 10
            vix_message = f"VIX at {vix:.2f} — elevated volatility, premiums expensive (-10% confidence)"
        elif vix > 20:
            vix_regime = "ELEVATED"; vix_penalty = 5
            vix_message = f"VIX at {vix:.2f} — slightly elevated, use caution (-5% confidence)"
        else:
            vix_regime = "NORMAL"; vix_penalty = 0
            vix_message = None

        spot = float(df.iloc[-1]["Close"])

        # Calculate DTE for today
        today = datetime.now()
        dte = get_dte(today)
        next_expiry = get_next_expiry(today)

        response = {
            "timestamp": datetime.now().isoformat(),
            "spot": spot,
            "vix": float(vix),
            "vix_regime": vix_regime,
            "vix_penalty": vix_penalty,
            "signal": signal_result["signal"],
            "direction": signal_result["direction"],
            "confidence": float(signal_result["confidence"]),
            "bull_confidence": float(signal_result["bull_confidence"]),
            "bear_confidence": float(signal_result["bear_confidence"]),
            "adx_trend_strength": signal_result.get("adx_trend_strength", "NEUTRAL"),
            "vix_warning": vix > 20,
            "vix_warning_message": vix_message,
            "strikes": strikes,
            "indicators": signal_result.get("indicators", {}),
            "ohlcv": df.tail(1).to_dict(orient="records"),
            "dte": dte,
            "next_expiry": next_expiry.strftime("%Y-%m-%d"),
        }

        # Log to DB (fire-and-forget, don't fail the request if it errors)
        try:
            log_signal({
                "signal": signal_result["signal"],
                "direction": signal_result["direction"],
                "confidence": float(signal_result["confidence"]),
                "spot": spot,
                "vix": float(vix),
                "indicators": signal_result.get("indicators", {}),
            })
        except Exception:
            pass

        return response

    except Exception as e:
        logger.error(f"Error in /api/signal: {str(e)}")
        return {
            "error": str(e),
            "message": "Failed to fetch signal data",
            "timestamp": datetime.now().isoformat()
        }


# ── Chart data ────────────────────────────────────────────────────────────────

@app.get("/api/chart-data")
def get_chart_data(
    interval: str = Query("1d", description="Interval: 1d, 1h, 15m"),
    period: str = Query("6mo", description="Period: 6mo, 3mo, 1y")
):
    """
    Return historical OHLCV + indicator data for charting.
    """
    try:
        df = fetch_nifty(period, interval)
        df = compute_all_indicators(df)

        # Convert to list of records, handling NaN
        records = []
        for idx, row in df.iterrows():
            def safe(v):
                import math
                if v is None:
                    return None
                try:
                    if math.isnan(float(v)):
                        return None
                    return round(float(v), 4)
                except Exception:
                    return str(v)

            records.append({
                "date": idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx),
                "open": safe(row.get("Open")),
                "high": safe(row.get("High")),
                "low": safe(row.get("Low")),
                "close": safe(row.get("Close")),
                "volume": safe(row.get("Volume")),
                "rsi": safe(row.get("RSI")),
                "macd": safe(row.get("MACD")),
                "macd_signal": safe(row.get("MACD_Signal")),
                "macd_hist": safe(row.get("MACD_Hist")),
                "bb_upper": safe(row.get("BB_Upper")),
                "bb_mid": safe(row.get("BB_Mid")),
                "bb_lower": safe(row.get("BB_Lower")),
                "ema9": safe(row.get("EMA9")),
                "ema21": safe(row.get("EMA21")),
                "ema50": safe(row.get("EMA50")),
                "ema200": safe(row.get("EMA200")),
                "adx": safe(row.get("ADX")),
                "supertrend": safe(row.get("Supertrend")),
                "supertrend_dir": safe(row.get("Supertrend_Dir")),
                "stoch_k": safe(row.get("Stoch_K")),
                "stoch_d": safe(row.get("Stoch_D")),
                "atr": safe(row.get("ATR")),
                "volume_ratio": safe(row.get("Volume_Ratio")),
            })

        return {
            "interval": interval,
            "period": period,
            "count": len(records),
            "data": records,
        }

    except Exception as e:
        logger.error(f"Error in /api/chart-data: {str(e)}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# ── Options chain ──────────────────────────────────────────────────────────────

@app.get("/api/options-chain")
def get_options_chain():
    try:
        options_data = get_nse_options_data()
        if options_data is None:
            return {
                "error": "Failed to fetch NSE options data",
                "message": "NSE API may be unavailable or rate-limited",
                "timestamp": datetime.now().isoformat()
            }
        return options_data
    except Exception as e:
        logger.error(f"Error in /api/options-chain: {str(e)}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


# ── Backtest (with DB cache) ───────────────────────────────────────────────────

@app.get("/api/backtest")
def get_backtest(
    period: str = Query("1y"),
    interval: str = Query("1d"),
    confidence_threshold: float = Query(60.0, ge=40, le=90),
    signal_type: str = Query("both"),
    force_refresh: bool = Query(False, description="Bypass cache and re-run")
):
    """
    Run historical backtest. Results are cached per (period, threshold, signal_type)
    for the current calendar day. Pass force_refresh=true to bypass the cache.
    """
    try:
        # Check cache first
        if not force_refresh:
            cached = get_cached_backtest(period, confidence_threshold, signal_type)
            if cached:
                cached["_cached"] = True
                return cached

        result = run_backtest(
            period=period,
            interval=interval,
            confidence_threshold=confidence_threshold,
            signal_type=signal_type
        )

        # Cache the result (only if it succeeded)
        if "error" not in result:
            try:
                save_backtest_cache(period, confidence_threshold, signal_type, result)
            except Exception:
                pass

        result["_cached"] = False
        return result

    except Exception as e:
        logger.error(f"Error in /api/backtest: {str(e)}")
        return {"error": str(e), "timestamp": datetime.now().isoformat()}


@app.delete("/api/backtest/cache")
def bust_backtest_cache():
    """Clear all cached backtest results."""
    clear_backtest_cache()
    return {"status": "ok", "message": "Backtest cache cleared"}


# ── Dry Run (Paper Trading) ────────────────────────────────────────────────────

class DryRunEntryRequest(BaseModel):
    notes: str = ""


@app.post("/api/dry-run/enter")
def dry_run_enter(body: DryRunEntryRequest = DryRunEntryRequest()):
    """
    Enter a paper trade based on the current live signal.
    Rejects if signal is STAY OUT or DTE < 2.
    """
    try:
        df = fetch_nifty("6mo", "1d")
        vix = fetch_vix()
        df = compute_all_indicators(df)
        signal_result = generate_signal(df, vix)

        if signal_result["signal"] == "STAY OUT":
            raise HTTPException(status_code=400, detail="Current signal is STAY OUT — no trade entered")

        today = datetime.now()
        dte = get_dte(today)
        if dte < 2:
            raise HTTPException(
                status_code=400,
                detail=f"DTE={dte} — too close to expiry, trade skipped"
            )

        spot = float(df.iloc[-1]["Close"])
        atr = float(df.iloc[-1]["ATR"])
        signal = signal_result["signal"]

        if signal == "BUY CE":
            sl = spot - 1.5 * atr
            target = spot + 2.5 * atr
        else:  # BUY PE
            sl = spot + 1.5 * atr
            target = spot - 2.5 * atr

        max_hold = min(dte, 5)
        strike_price = int(round(spot / 100) * 100)
        strike_label = f"{strike_price} {'CE' if signal == 'BUY CE' else 'PE'}"

        trade = {
            "entry_date": today.strftime("%Y-%m-%d"),
            "signal": signal,
            "strike": strike_label,
            "entry_spot": spot,
            "sl": round(sl, 2),
            "target": round(target, 2),
            "dte": dte,
            "max_hold_days": max_hold,
            "confidence": float(signal_result["confidence"]),
            "vix": float(vix),
        }

        trade_id = create_dry_run_trade(trade)
        trade["id"] = trade_id
        trade["status"] = "OPEN"
        trade["notes"] = body.notes

        return {"status": "ok", "trade": trade}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /api/dry-run/enter: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dry-run/trades")
def dry_run_list(status: str = Query(None, description="Filter: OPEN, CLOSED")):
    """Return all paper trades, optionally filtered by status."""
    trades = get_dry_run_trades(status)
    return {"trades": trades, "count": len(trades)}


@app.post("/api/dry-run/update")
def dry_run_update():
    """
    Fetch current Nifty price and update all OPEN paper trades:
    - Close if target hit
    - Close if stop-loss hit
    - Close if max_hold_days exceeded (exit at current price)
    Returns list of trades that were closed in this update.
    """
    try:
        df = fetch_nifty("5d", "1d")
        current_spot = float(df.iloc[-1]["Close"])
        today = datetime.now()

        open_trades = get_dry_run_trades("OPEN")
        closed_now = []

        for trade in open_trades:
            entry_date = datetime.strptime(trade["entry_date"], "%Y-%m-%d")
            days_held = (today - entry_date).days
            signal = trade["signal"]
            sl = trade["sl"]
            target = trade["target"]
            max_hold = trade["max_hold_days"]
            entry_spot = trade["entry_spot"]
            atr_approx = abs(target - entry_spot) / 2.5  # reverse-engineer ATR

            exit_spot = None
            exit_reason = None
            result = None

            if signal == "BUY CE":
                if current_spot >= target:
                    exit_spot, exit_reason, result = target, "TARGET", "WIN"
                elif current_spot <= sl:
                    exit_spot, exit_reason, result = sl, "STOP_LOSS", "LOSS"
            else:  # BUY PE
                if current_spot <= target:
                    exit_spot, exit_reason, result = target, "TARGET", "WIN"
                elif current_spot >= sl:
                    exit_spot, exit_reason, result = sl, "STOP_LOSS", "LOSS"

            # Time-based exit
            if exit_spot is None and days_held >= max_hold:
                exit_spot = current_spot
                exit_reason = "EXPIRY"
                result = "WIN" if (
                    (signal == "BUY CE" and current_spot > entry_spot) or
                    (signal == "BUY PE" and current_spot < entry_spot)
                ) else "LOSS"

            if exit_spot is not None:
                # Estimate option P&L
                spot_move = abs(exit_spot - entry_spot)
                delta = 0.45
                vix_mult = max(0.5, trade.get("vix", 15.0) / 15.0)
                premium = entry_spot * 0.015 * vix_mult
                direction = (
                    (1 if exit_spot > entry_spot else -1) if signal == "BUY CE"
                    else (-1 if exit_spot < entry_spot else 1)
                )
                pct_return = float(
                    np.clip((direction * spot_move * delta / premium) * 100, -100, 300)
                ) if premium > 0 else 0.0

                close_dry_run_trade(trade["id"], exit_spot, exit_reason, pct_return, result)
                closed_now.append({
                    **trade,
                    "exit_spot": exit_spot,
                    "exit_reason": exit_reason,
                    "pct_return": round(pct_return, 1),
                    "result": result,
                })

        return {
            "current_spot": current_spot,
            "trades_checked": len(open_trades),
            "trades_closed": len(closed_now),
            "closed": closed_now,
        }

    except Exception as e:
        logger.error(f"Error in /api/dry-run/update: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/dry-run/trades/{trade_id}")
def dry_run_delete(trade_id: int):
    """Delete a specific paper trade."""
    delete_dry_run_trade(trade_id)
    return {"status": "ok", "deleted_id": trade_id}


@app.delete("/api/dry-run/trades")
def dry_run_clear():
    """Delete all paper trades."""
    clear_dry_run_trades()
    return {"status": "ok", "message": "All paper trades cleared"}


# ── Signal history ─────────────────────────────────────────────────────────────

@app.get("/api/signal-history")
def signal_history(limit: int = Query(50, ge=1, le=500)):
    """Return the most recent signal log entries."""
    history = get_signal_history(limit)
    return {"history": history, "count": len(history)}


# ── CAS (Closing Auction Session) live signal ──────────────────────────────────

@app.get("/api/cas-signal")
def get_cas_signal(force_refresh: bool = Query(False, description="Bypass the 15s result cache")):
    """
    Live CAS closing-window signal: big-move risk, directional bias (BULLISH/
    BEARISH) with calibrated POP, suggested strike/action, and the validated
    high-conviction mean-reversion rule check.

    Backed by cas_service.py, which trains the underlying RandomForest models
    ONCE (cached in memory, auto-refreshed daily) and only re-fetches live
    market data (spot, VIX, F&O, cross-asset, NSE option chain — fetched in
    parallel) on each request, with a 15-second result cache so rapid UI
    polling stays fast (typically <100ms on cache hit, ~2-3s on cache miss).
    """
    try:
        return cas_service.get_live_cas_signal(force_refresh=force_refresh)
    except Exception as e:
        logger.error(f"Error in /api/cas-signal: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to compute CAS signal — live market data may be temporarily unavailable",
            "timestamp": datetime.now().isoformat(),
        }


# ── Zerodha Kite Connect integration ────────────────────────────────────────────
# Fully optional — the app works normally without any Zerodha credentials.
# Configure ZERODHA_API_KEY / ZERODHA_API_SECRET in backend/.env to enable
# these endpoints (see backend/.env.example and backend/zerodha_client.py
# for the full setup guide).

class ZerodhaLoginCallbackRequest(BaseModel):
    request_token: str


class ZerodhaOrderRequest(BaseModel):
    tradingsymbol: str
    exchange: str = "NFO"
    transaction_type: str  # "BUY" or "SELL"
    quantity: int
    order_type: str = "MARKET"
    product: str = "MIS"
    price: float = None
    trigger_price: float = None


@app.get("/api/zerodha/status")
def zerodha_status():
    """
    Non-throwing connection status check — safe to poll from the UI to show
    a "Connected / Not Connected" badge. Never errors, even if Zerodha is
    completely unconfigured.
    """
    return zerodha_client.get_connection_status()


@app.get("/api/zerodha/login-url")
def zerodha_login_url():
    """
    Returns the Zerodha Kite login URL. The frontend should redirect the
    user's browser to this URL; after login, Zerodha redirects back to the
    redirect URL configured in your Kite Connect app settings with a
    `request_token` query param, which should then be POSTed to
    /api/zerodha/callback to complete the connection.
    """
    try:
        return {"login_url": zerodha_client.get_login_url()}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/zerodha/callback")
def zerodha_callback(body: ZerodhaLoginCallbackRequest):
    """
    Exchange the request_token (from the Zerodha login redirect) for an
    access_token, and cache it. Call this once after the user completes the
    Zerodha login flow.
    """
    try:
        profile = zerodha_client.complete_login(body.request_token)
        return {"status": "ok", "profile": profile}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Zerodha login callback failed: {e}")
        raise HTTPException(status_code=400, detail=f"Login failed: {e}")


@app.post("/api/zerodha/disconnect")
def zerodha_disconnect():
    """Clear the cached access token (does not revoke it on Zerodha's side)."""
    zerodha_client.clear_access_token()
    return {"status": "ok", "message": "Disconnected. You can reconnect anytime."}


class ZerodhaAutoLoginRequest(BaseModel):
    user_id: str
    password: str
    totp_secret: str
    remember: bool = True


@app.post("/api/zerodha/auto-login")
def zerodha_auto_login(body: ZerodhaAutoLoginRequest):
    """
    Fully automated login using your Zerodha user ID + password + TOTP
    secret — no manual browser step needed. See zerodha_autologin.py for
    exactly how this works and its risks/caveats (it automates Zerodha's
    actual login website via undocumented endpoints, since the OFFICIAL
    Kite Connect API has no password-based login by design).

    If `remember` is true, credentials are cached (encrypted at rest via
    OS-level file permissions on the .env-like store) so the background
    auto-reconnect job can refresh the session automatically each morning
    without you needing to call this endpoint again.
    """
    if not zerodha_autologin.is_available():
        raise HTTPException(
            status_code=400,
            detail="pyotp not installed on the server. Run: pip install pyotp",
        )
    api_key = zerodha_client.get_api_key()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Zerodha API key not configured. Add ZERODHA_API_KEY to backend/.env first.",
        )
    try:
        request_token = zerodha_autologin.auto_login_and_get_request_token(
            user_id=body.user_id,
            password=body.password,
            totp_secret=body.totp_secret,
            api_key=api_key,
        )
        profile = zerodha_client.complete_login(request_token)

        if body.remember:
            from database import set_setting
            set_setting("zerodha_autologin_user_id", body.user_id)
            set_setting("zerodha_autologin_password", body.password)
            set_setting("zerodha_autologin_totp_secret", body.totp_secret)
            set_setting("zerodha_autologin_enabled", "true")

        return {"status": "ok", "profile": profile, "remembered": body.remember}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Zerodha auto-login failed: {e}")
        raise HTTPException(status_code=400, detail=f"Auto-login failed: {e}")


@app.post("/api/zerodha/auto-login/forget")
def zerodha_auto_login_forget():
    """Deletes any remembered auto-login credentials from the local DB."""
    from database import set_setting
    set_setting("zerodha_autologin_user_id", "")
    set_setting("zerodha_autologin_password", "")
    set_setting("zerodha_autologin_totp_secret", "")
    set_setting("zerodha_autologin_enabled", "false")
    return {"status": "ok", "message": "Auto-login credentials forgotten."}


@app.get("/api/zerodha/auto-login/status")
def zerodha_auto_login_status():
    """Whether auto-login credentials are currently remembered (never returns the actual secrets)."""
    from database import get_setting
    enabled = get_setting("zerodha_autologin_enabled") == "true"
    user_id = get_setting("zerodha_autologin_user_id") or ""
    return {
        "remembered": enabled and bool(user_id),
        "user_id": user_id if enabled else None,
        "pyotp_available": zerodha_autologin.is_available(),
    }


@app.get("/api/zerodha/profile")
def zerodha_profile():
    try:
        return zerodha_client.get_profile()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/zerodha/margins")
def zerodha_margins():
    try:
        return zerodha_client.get_margins()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/zerodha/positions")
def zerodha_positions():
    try:
        return zerodha_client.get_positions()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/zerodha/holdings")
def zerodha_holdings():
    try:
        return zerodha_client.get_holdings()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/zerodha/orders")
def zerodha_orders():
    try:
        return zerodha_client.get_orders()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/zerodha/quote")
def zerodha_quote(instruments: str = Query(..., description="Comma-separated, e.g. 'NSE:NIFTY 50,NFO:NIFTY24DEC24200CE")):
    """instruments: comma-separated list, e.g. 'NSE:NIFTY 50,NFO:NIFTY24DEC24200CE'"""
    try:
        instrument_list = [s.strip() for s in instruments.split(",") if s.strip()]
        return zerodha_client.get_quote(instrument_list)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/ibkr/fx-rate")
def ibkr_fx_rate(base: str = "USD", quote: str = "INR"):
    """Fetch live FX rate from IBKR (e.g. USD/INR). Falls back to 83.50 if IBKR not connected."""
    try:
        return broker_manager.get_broker("ibkr").get_fx_rate(base, quote)
    except Exception as e:
        logger.warning(f"FX rate fetch failed: {e}")
        return {"base": base, "quote": quote, "rate": 83.50, "source": "fallback"}

@app.get("/api/ibkr/search")
def ibkr_search(query: str = Query(..., description="Symbol to search for, e.g. 'QCOM'")):
    """Search for valid IBKR symbols and return matching contracts."""
    try:
        return broker_manager.get_broker("ibkr").search_symbols(query)
    except Exception as e:
        logger.error(f"IBKR search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ibkr/strikes")
def ibkr_strikes(symbol: str):
    """Fetch actual tradable strikes and expiries for a symbol from IBKR."""
    try:
        return broker_manager.get_broker("ibkr").get_available_strikes(symbol)
    except Exception as e:
        logger.error(f"IBKR strikes fetch failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ibkr/contract-details")
def ibkr_contract_details(symbol: str, strike: float, expiry: str, option_type: str = None):
    """Fetch live data (LTP, OI, Volume) for a specific IBKR contract."""
    try:
        return broker_manager.get_broker("ibkr").get_contract_details(symbol, strike, expiry, option_type)
    except Exception as e:
        logger.error(f"IBKR contract details failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/zerodha/order")
def zerodha_place_order(body: ZerodhaOrderRequest):
    """
    Places a REAL order on Zerodha with real money. Only usable once
    Zerodha is connected. For risk-free testing, use the existing
    /api/dry-run endpoints instead — they never touch a real broker.
    """
    try:
        return zerodha_client.place_order(
            tradingsymbol=body.tradingsymbol,
            exchange=body.exchange,
            transaction_type=body.transaction_type,
            quantity=body.quantity,
            order_type=body.order_type,
            product=body.product,
            price=body.price,
            trigger_price=body.trigger_price,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Zerodha order placement failed: {e}")
        raise HTTPException(status_code=400, detail=f"Order failed: {e}")


@app.delete("/api/zerodha/order/{order_id}")
def zerodha_cancel_order(order_id: str, variety: str = Query("regular")):
    try:
        return zerodha_client.cancel_order(order_id, variety=variety)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Zerodha order cancel failed: {e}")
        raise HTTPException(status_code=400, detail=f"Cancel failed: {e}")


@app.get("/api/zerodha/trades")
def zerodha_trades():
    """Today's executed trades (fills). Each order can have multiple partial fills."""
    try:
        return {"trades": zerodha_client.get_trades()}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/zerodha/order/{order_id}/history")
def zerodha_order_history(order_id: str):
    """Full state history of a single order (placed → open → complete/rejected)."""
    try:
        return {"history": zerodha_client.get_order_history(order_id)}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/zerodha/gtts")
def zerodha_list_gtts():
    """
    Lists all active GTT (Good Till Triggered) orders. The auto-trader places
    a GTT OCO exit alongside every entry — this endpoint lets the UI show and
    manage those pending exits.
    """
    try:
        return {"gtts": zerodha_client.get_gtts()}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/zerodha/gtt/{trigger_id}")
def zerodha_delete_gtt(trigger_id: int):
    """
    Cancels a GTT order. Call this when manually closing a position that has
    an associated auto-trader GTT exit — the GTT must be cancelled too,
    otherwise it will fire on a position that no longer exists.
    """
    try:
        return zerodha_client.delete_gtt(trigger_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"GTT delete failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


class ZerodhaModifyOrderRequest(BaseModel):
    quantity: int = None
    price: float = None
    trigger_price: float = None
    order_type: str = None
    variety: str = "regular"


@app.put("/api/zerodha/order/{order_id}")
def zerodha_modify_order(order_id: str, body: ZerodhaModifyOrderRequest):
    """Modifies an open (pending) order — e.g. change a limit price or quantity."""
    try:
        return zerodha_client.modify_order(
            order_id=order_id,
            quantity=body.quantity,
            price=body.price,
            trigger_price=body.trigger_price,
            order_type=body.order_type,
            variety=body.variety,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Order modify failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


class ZerodhaConvertPositionRequest(BaseModel):
    tradingsymbol: str
    exchange: str
    transaction_type: str
    position_type: str  # "day" or "overnight"
    quantity: int
    old_product: str   # e.g. "MIS"
    new_product: str   # e.g. "NRML"


@app.post("/api/zerodha/position/convert")
def zerodha_convert_position(body: ZerodhaConvertPositionRequest):
    """
    Converts a position from one product type to another (e.g. MIS → NRML to
    carry an intraday F&O position overnight without auto-square-off).
    """
    try:
        result = zerodha_client.convert_position(
            tradingsymbol=body.tradingsymbol,
            exchange=body.exchange,
            transaction_type=body.transaction_type,
            position_type=body.position_type,
            quantity=body.quantity,
            old_product=body.old_product,
            new_product=body.new_product,
        )
        return {"status": "ok", "converted": result}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Position convert failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# ── IBKR extended endpoints ──────────────────────────────────────────────────

@app.get("/api/ibkr/historical")
def ibkr_historical(
    symbol: str = Query(..., description="e.g. QCOM, AAPL, NVDA"),
    duration: str = Query("1 Y", description="e.g. '1 Y', '6 M', '3 M', '1 W'"),
    bar_size: str = Query("1 day", description="e.g. '1 day', '1 hour', '30 mins'"),
):
    """
    Historical OHLCV bars for any IBKR-listed stock. Returns the same shape
    as /api/chart-data so the frontend Charts page can display US stocks too.
    Requires IBKR to be connected (TWS/IB Gateway running).
    """
    try:
        bars = broker_manager.get_broker("ibkr").get_historical_data(
            symbol=symbol, duration=duration, bar_size=bar_size
        )
        return {"symbol": symbol, "duration": duration, "bar_size": bar_size, "count": len(bars), "data": bars}
    except Exception as e:
        logger.error(f"IBKR historical data failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ibkr/orders")
def ibkr_open_orders():
    """Returns all open (pending) orders on the connected IBKR account."""
    try:
        return {"orders": broker_manager.get_broker("ibkr").get_open_orders()}
    except Exception as e:
        logger.error(f"IBKR open orders failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ibkr/executions")
def ibkr_executions():
    """Returns today's executed trades (fills) from IBKR."""
    try:
        return {"executions": broker_manager.get_broker("ibkr").get_executions()}
    except Exception as e:
        logger.error(f"IBKR executions failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ibkr/account-summary")
def ibkr_account_summary():
    """
    Returns a structured IBKR account summary: net liquidation, buying power,
    cash balance, unrealized P&L, realized P&L. More structured than /margins.
    """
    try:
        return broker_manager.get_broker("ibkr").get_account_summary()
    except Exception as e:
        logger.error(f"IBKR account summary failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Dataset auto-update (keeps CAS models learning from new live data) ─────────

@app.get("/api/dataset/status")
def dataset_status():
    """
    Reports how fresh the CAS training dataset is — i.e. whether the models
    are learning from recent trading days or stuck on an old snapshot.
    """
    import pandas as pd
    v1_path = dataset_updater.V1_PATH
    v2_path = dataset_updater.V2_PATH

    def _file_info(path):
        if not os.path.exists(path):
            return {"exists": False}
        df = pd.read_csv(path, usecols=["date"])
        last_date = str(df["date"].max())
        mtime = datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
        return {
            "exists": True,
            "rows": len(df),
            "last_trading_day": last_date,
            "file_last_modified": mtime,
        }

    return {
        "master_dataset": _file_info(v1_path),
        "master_dataset_v2": _file_info(v2_path),
        "auto_update_check_interval_hours": dataset_updater.CHECK_INTERVAL_SECONDS // 3600,
        "note": (
            "The background updater checks for newly-completed trading days "
            "every few hours and appends them automatically. Once new rows "
            "are added, the CAS models retrain on the larger dataset on the "
            "next live request (see /api/cas-signal)."
        ),
    }


@app.post("/api/dataset/update-now")
def dataset_update_now():
    """
    Manually trigger a dataset update cycle right now (instead of waiting
    for the periodic background check). Runs synchronously and returns how
    many new trading day(s) were incorporated (0 if nothing new is
    available yet — e.g. if today's NSE bhavcopy hasn't been published).
    """
    try:
        n_before = 0
        if os.path.exists(dataset_updater.V1_PATH):
            import pandas as pd
            n_before = len(pd.read_csv(dataset_updater.V1_PATH, usecols=["date"]))

        dataset_updater.run_daily_update_cycle()

        n_after = 0
        if os.path.exists(dataset_updater.V1_PATH):
            import pandas as pd
            n_after = len(pd.read_csv(dataset_updater.V1_PATH, usecols=["date"]))

        return {
            "status": "ok",
            "rows_before": n_before,
            "rows_after": n_after,
            "new_rows_added": n_after - n_before,
        }
    except Exception as e:
        logger.error(f"Manual dataset update failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Auto-Trader ──────────────────────────────────────────────────────────────
# See auto_trader.py for the full safety design. DISABLED BY DEFAULT and
# forced OFF on every server restart — must be explicitly re-enabled here
# each time via POST /api/auto-trader/enable.

class AutoTraderConfigRequest(BaseModel):
    mode: str = None            # "high_conviction_only" | "directional_signal"
    lots: int = None
    max_daily_loss: float = None


@app.get("/api/auto-trader/status")
def auto_trader_status():
    """
    Full status snapshot: enabled/disabled, current config, today's trade
    count, today's realized P&L, and whether Zerodha is actually connected
    (auto-trading is inert without a live Zerodha connection regardless of
    the enabled flag).
    """
    config = auto_trader.get_config()
    config["zerodha_connected"] = zerodha_client.get_connection_status().get("connected", False)
    return config


@app.post("/api/auto-trader/enable")
def auto_trader_enable():
    """
    Explicitly turn auto-trading ON. Requires Zerodha to already be
    connected — refuses otherwise so you can't enable a feature that would
    just silently do nothing (or worse, misleadingly appear active).
    """
    status = zerodha_client.get_connection_status()
    if not status.get("connected"):
        raise HTTPException(
            status_code=400,
            detail="Cannot enable auto-trading: Zerodha is not connected. "
                   "Connect via Settings → Zerodha Integration first.",
        )
    auto_trader.set_enabled(True)
    return {"status": "ok", "enabled": True}


@app.post("/api/auto-trader/disable")
def auto_trader_disable():
    """Turn auto-trading OFF immediately — the kill switch."""
    auto_trader.set_enabled(False)
    return {"status": "ok", "enabled": False}


@app.post("/api/auto-trader/config")
def auto_trader_config(body: AutoTraderConfigRequest):
    """Update auto-trader configuration (mode, lots, max daily loss)."""
    try:
        if body.mode is not None:
            auto_trader.set_mode(body.mode)
        if body.lots is not None:
            auto_trader.set_lots(body.lots)
        if body.max_daily_loss is not None:
            auto_trader.set_max_daily_loss(body.max_daily_loss)
        return {"status": "ok", "config": auto_trader.get_config()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/auto-trader/log")
def auto_trader_log(limit: int = Query(100, ge=1, le=500)):
    """
    Full audit trail of every auto-trader decision (trades placed, signals
    skipped and why, errors). This is the safety-critical visibility layer
    for a feature that can touch real money.
    """
    entries = get_auto_trade_log(limit)
    return {"entries": entries, "count": len(entries)}


# ── Live Position Risk Monitoring ───────────────────────────────────────────
# Shows ALL open positions in your real Zerodha account (however they were
# opened — manually, via Dry Run, or via Auto-Trader) with live P&L and
# risk alerts cross-referenced against the CURRENT CAS signal. Read-only —
# never places or modifies any order.

@app.get("/api/positions/live")
def positions_live():
    """
    Returns every open NIFTY option position with live P&L and risk alerts
    (signal flipped against you, big-move risk is HIGH, deep loss, near
    target). Safe to poll frequently — reuses the CAS signal's own 15s
    cache under the hood.
    """
    data = position_risk.get_live_positions_with_risk()
    
    # Add Professional Portfolio Greeks
    if data.get("success") and "positions" in data:
        greeks = VolatilityAnalytics.calculate_portfolio_greeks(data["positions"])
        data["portfolio_greeks"] = greeks
        
    return data


# ── Short Iron Condor ────────────────────────────────────────────────────────
# See iron_condor.py for the full strategy logic. This is a defined-risk,
# range-bound premium-selling strategy. Strike suggestions are computed from
# the live NSE option chain; order placement uses your connected Zerodha
# account and places all 4 legs as separate market orders.

class IronCondorOrderRequest(BaseModel):
    otm_distance_pct: float = 2.5
    wing_width_points: int = 200
    strike_step: int = 50
    lots: int = 1


class IronCondorMarginCheckRequest(BaseModel):
    otm_distance_pct: float = 2.5
    wing_width_points: int = 200
    strike_step: int = 50
    lots: int = 1
    available_balance: float = None


@app.get("/api/iron-condor/suggest")
def iron_condor_suggest(
    otm_distance_pct: float = Query(2.5, ge=0.5, le=10, description="How far OTM (%) to place short strikes"),
    wing_width_points: int = Query(200, ge=50, le=1000, description="Distance between short and long (hedge) strikes"),
    strike_step: int = Query(50, description="Strike rounding step (NIFTY uses 50)"),
):
    """
    Suggests 4 strikes for a short iron condor based on the live NIFTY
    option chain, with computed max profit/loss (PER SHARE), breakevens,
    an approximate probability of profit, a payoff diagram, the CURRENT
    live NIFTY lot size, and the margin required for exactly 1 lot.

    IMPORTANT: this endpoint does NOT take `lots` or `available_balance` —
    those don't change the strikes/premiums at all (a 3-lot iron condor has
    identical strikes to a 1-lot one), so scaling by lot count and checking
    against a balance is done entirely CLIENT-SIDE in the frontend using
    the per-share/per-lot figures returned here. This keeps changing the
    lot count or typing a balance instant (no network round-trip / NSE
    re-fetch needed) instead of laggy and flickering.
    """
    try:
        strikes = iron_condor.suggest_iron_condor_strikes(
            otm_distance_pct=otm_distance_pct,
            wing_width_points=wing_width_points,
            strike_step=strike_step,
        )
        lot_size = iron_condor.get_lot_size()
        payoff = iron_condor.build_payoff_diagram(strikes, lot_size=lot_size)
        strikes["payoff_diagram"] = payoff
        strikes["lot_size"] = lot_size

        # Margin per SINGLE lot only — independent of how many lots the user
        # is considering, so the frontend can instantly scale this by any
        # lot count without another network call. Live Kite cross-margin
        # calc if connected, else an approximate max-loss-based estimate.
        try:
            margin_info = iron_condor.estimate_margin_per_lot(strikes)
        except Exception as e:
            margin_info = {"margin_per_lot": None, "source": "error", "error": str(e)}
        strikes["margin_per_lot"] = margin_info.get("margin_per_lot")
        strikes["margin_source"] = margin_info.get("source")

        # If Zerodha is connected, ALSO report the current live balance —
        # purely informational (one cheap read, not re-fetched per
        # keystroke), so the frontend can pre-fill the balance field as a
        # convenience. The user can freely override it; it's never silently
        # re-fetched or overwritten while they're typing.
        strikes["live_available_balance"] = None
        if zerodha_client.get_connection_status().get("connected"):
            try:
                bal = zerodha_client.get_available_balance()
                strikes["live_available_balance"] = bal.get("available_margin") or bal.get("available_cash")
            except Exception:
                pass

        return {"success": True, **strikes}
    except RuntimeError as e:
        return {"success": False, "message": str(e)}
    except Exception as e:
        logger.error(f"Error in /api/iron-condor/suggest: {e}")
        return {"success": False, "message": str(e)}


@app.post("/api/iron-condor/check-margin")
def iron_condor_check_margin(body: IronCondorMarginCheckRequest):
    """
    Standalone margin/balance sufficiency check for a given iron condor
    configuration + lot count + optional manual balance, without placing
    any order. Works with or without Zerodha connected — falls back to an
    approximate max-loss-based margin estimate when Zerodha isn't available.
    """
    try:
        strikes = iron_condor.suggest_iron_condor_strikes(
            otm_distance_pct=body.otm_distance_pct,
            wing_width_points=body.wing_width_points,
            strike_step=body.strike_step,
        )
        result = iron_condor.check_balance_and_margin(
            strikes, body.lots, available_balance_override=body.available_balance
        )
        return {"success": True, **result}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Iron condor margin check failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/iron-condor/place")
def iron_condor_place(body: IronCondorOrderRequest):
    """
    Places all 4 legs of a short iron condor as separate market orders on
    your connected Zerodha account. Uses REAL money. If any leg fails after
    others have already filled, the response clearly flags a PARTIAL FILL
    warning — an incomplete iron condor has undefined/uncapped risk and
    needs immediate manual attention.
    """
    try:
        strikes = iron_condor.suggest_iron_condor_strikes(
            otm_distance_pct=body.otm_distance_pct,
            wing_width_points=body.wing_width_points,
            strike_step=body.strike_step,
        )
        expiry_iso = datetime.strptime(strikes["expiry"], "%d-%b-%Y").strftime("%Y-%m-%d")
        result = iron_condor.place_iron_condor_order(strikes, expiry_iso, lots=body.lots)
        return {"strikes_used": strikes, **result}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Iron condor order placement failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/iron-condor/recommendation")
def iron_condor_recommendation():
    """
    Returns the recommended (OTM%, wing width) for TODAY, based on the
    2-year historical backtest (IRON_CONDOR_BACKTEST_FINDINGS.md) for
    today's day of week, DYNAMICALLY SCALED to the actual live DTE and IV
    right now — e.g. the Monday backtest was calibrated on ~2 DTE entries,
    but if today happens to be expiry day itself (DTE=0), a fixed 2.5% OTM
    would be far beyond any realistic move and yield near-zero premium.
    Falls back to the static backtest table if live chain data can't be
    fetched. This is informational only, not a live trade signal.
    """
    today_dow = datetime.now().strftime("%A")
    dte = None
    avg_iv_pct = None
    try:
        chain = get_nse_options_data()
        if chain:
            dte = chain.get("days_to_expiry")
            # Use ATM IV as a reasonable stand-in for the day's general IV level
            spot = chain.get("spot_price")
            all_strikes = chain.get("all_strikes", [])
            if spot and all_strikes:
                atm_strike = min(all_strikes, key=lambda s: abs(s.get("strikePrice", 0) - spot))
                ce_iv = (atm_strike.get("CE") or {}).get("impliedVolatility")
                pe_iv = (atm_strike.get("PE") or {}).get("impliedVolatility")
                ivs = [v for v in (ce_iv, pe_iv) if v]
                avg_iv_pct = sum(ivs) / len(ivs) if ivs else None
    except Exception as e:
        logger.warning(f"Could not fetch live chain for dynamic IC recommendation: {e}")

    rec = iron_condor.get_recommended_params(today_dow, dte=dte, avg_iv_pct=avg_iv_pct)
    return {
        "today": today_dow,
        "days_to_expiry": dte,
        "live_iv_pct": round(avg_iv_pct, 2) if avg_iv_pct else None,
        "recommended_otm_distance_pct": rec["otm_distance_pct"],
        "recommended_wing_width_points": rec["wing_width_points"],
        "note": rec["note"],
        "all_recommendations": iron_condor.BACKTESTED_RECOMMENDATIONS,
        "full_analysis_doc": "backend/IRON_CONDOR_BACKTEST_FINDINGS.md",
    }


@app.get("/api/iron-condor/live-status")
def iron_condor_live_status():
    """
    Detects an existing open iron-condor-shaped position from your ACTUAL
    live Zerodha positions and reports live aggregate P&L plus proximity
    alerts (spot approaching/breaching a short strike). Best-effort
    heuristic detection — always cross-check against your actual Zerodha app.
    """
    return iron_condor.get_live_iron_condor_status()

@app.get("/api/volatility/analysis")
def get_volatility_analysis(symbol: str = "^NSEI"):
    """
    Professional Volatility Analysis: VRP, IV Rank, IV Percentile, and Regime.
    """
    return get_enhanced_volatility_analysis(symbol)


# ── Live Equity Holdings Analysis ───────────────────────────────────────────
# Your long-term equity holdings (portfolio.holdings — separate from the F&O
# `positions` shown above), enriched with live P&L + technical analysis +
# a per-holding BUY_MORE/HOLD/TRIM/SELL suggestion. Read-only/advisory only.

@app.get("/api/holdings/live")
def holdings_live():
    """
    Returns every equity holding in your connected Zerodha account with
    live P&L, technical analysis (RSI, EMA trend stack, ADX — same engine
    used elsewhere in this app), and a definitive per-holding suggestion
    combining your actual cost-basis P&L with the live technical setup.
    """
    return holdings_analysis.get_live_holdings_with_analysis()




# ── Global Watchlist (Qualcomm, Google, Meta, Gold, Silver, TSMC, Nvidia,
# Micron, Samsung, Microsoft, Nasdaq-100) ───────────────────────────────────
# A fixed watchlist of non-Indian stocks/ETFs the user wants to swing-trade
# / hold long-term. Reuses the SAME generic indicators.py/signal_engine.py
# used for NIFTY (nothing NIFTY-specific in that math) plus new long-term
# trend context (200-day EMA, 52-week range, 1-year return) and a combined
# short-term + long-term recommendation. See backend/watchlist_analysis.py
# for full design rationale.

@app.get("/api/watchlist")
def get_watchlist(force_refresh: bool = Query(False, description="Bypass the 5-minute result cache")):
    """
    Live tracker + signal for the fixed global watchlist PLUS any user-added
    custom symbols (see /api/watchlist/search and /api/watchlist/add).
    Cached for 5 minutes (this is a swing/long-term watchlist, not a
    fast-moving intraday signal) — pass force_refresh=true to bypass. One
    bad/delisted ticker never breaks the rest of the list (each symbol's
    errors are isolated in its own result entry).
    """
    try:
        return watchlist_analysis.get_cached_watchlist_analysis(force_refresh=force_refresh)
    except Exception as e:
        logger.error(f"Error in /api/watchlist: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to fetch watchlist data",
            "timestamp": datetime.now().isoformat(),
        }


@app.get("/api/watchlist/search")
def watchlist_search(symbol: str = Query(..., description="Ticker symbol to validate, e.g. AAPL, RELIANCE.NS")):
    """
    Validates a user-searched ticker BEFORE adding it — confirms yfinance
    actually returns live data for it and looks up a human-readable name.
    Does NOT persist anything; call /api/watchlist/add to actually add it.
    """
    return watchlist_analysis.validate_symbol(symbol)


@app.get("/api/watchlist/suggest")
def watchlist_suggest(q: str = Query(..., min_length=1, description="Partial symbol/company name to autocomplete")):
    """
    Live autocomplete suggestions as the user types (company name OR
    partial ticker) — e.g. typing "nvid" suggests NVDA/Nvidia Corporation.
    Backed by Yahoo Finance's public search endpoint (the same underlying
    data source yfinance itself uses), so every suggestion returned here
    is guaranteed to also work with /api/watchlist/search and /add. Never
    errors — returns an empty list if the query is too short or the
    external search is temporarily unavailable, so a flaky lookup never
    blocks the user from just typing the exact symbol themselves.
    """
    return {"suggestions": watchlist_analysis.search_suggestions(q)}


class WatchlistAddRequest(BaseModel):
    symbol: str
    name: str = None


@app.post("/api/watchlist/add")
def watchlist_add(body: WatchlistAddRequest):
    """
    Adds a custom symbol to the watchlist (persisted in SQLite, survives
    restarts). Re-validates the symbol server-side even if the frontend
    already called /api/watchlist/search, so this endpoint can never end
    up persisting an unfetchable ticker. Uses the VALIDATED/resolved symbol
    (e.g. a bare "RELIANCE" search resolves to "RELIANCE.NS") rather than
    the user's raw input, so NSE/BSE Indian stocks work with either the
    bare name or the explicit .NS/.BO suffix. Busts the watchlist cache so
    the new symbol shows up on the very next /api/watchlist call.
    """
    from database import add_custom_watchlist_symbol

    validation = watchlist_analysis.validate_symbol(body.symbol)
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation["error"] or "Invalid symbol")

    symbol = validation.get("resolved_symbol") or body.symbol.strip().upper()
    name = body.name or validation["name"] or symbol
    add_custom_watchlist_symbol(symbol, name)

    # Force the next /api/watchlist read to recompute (picks up the new symbol)
    watchlist_analysis.get_cached_watchlist_analysis(force_refresh=True)

    return {"status": "ok", "symbol": symbol, "name": name}


@app.delete("/api/watchlist/{symbol}")
def watchlist_remove(symbol: str):
    """Removes a custom symbol from the watchlist. Cannot remove built-in
    watchlist symbols (they're not stored in the custom table at all, so
    this is a no-op for them rather than an error)."""
    from database import remove_custom_watchlist_symbol

    remove_custom_watchlist_symbol(symbol)
    watchlist_analysis.get_cached_watchlist_analysis(force_refresh=True)
    return {"status": "ok", "removed": symbol.upper()}


# ── eToro Portfolio Tracker (MANUAL entry — see etoro_analysis.py) ─────────
# eToro has no self-serve public API for retail accounts (confirmed via
# direct testing — their endpoints return 401/403 without partner-level
# credentials, and no maintained Python client exists), unlike Zerodha's
# Kite Connect. So this lets the user manually record what they hold on
# eToro and get the SAME live technical analysis + P&L-aware suggestion
# used elsewhere in this app.

class EtoroHoldingRequest(BaseModel):
    symbol: str
    name: str = None
    quantity: float
    entry_price: float
    notes: str = ""


@app.get("/api/etoro/portfolio")
def etoro_portfolio():
    """
    Returns every manually-entered eToro holding with live price, real P&L
    (based on YOUR entry price/quantity), the same technical signal engine
    used elsewhere in this app, and a combined BUY MORE/HOLD/TRIM/SELL
    suggestion. Includes a portfolio-level P&L summary.
    """
    try:
        return etoro_analysis.get_portfolio_with_analysis()
    except Exception as e:
        logger.error(f"Error in /api/etoro/portfolio: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to fetch eToro portfolio data",
            "timestamp": datetime.now().isoformat(),
        }


@app.post("/api/etoro/holdings")
def etoro_add_holding(body: EtoroHoldingRequest):
    """
    Manually record a new eToro holding. Validates the symbol resolves to
    real live data (same validate_symbol() used by the watchlist, including
    NSE/BSE bare-symbol auto-resolution) BEFORE saving, so a typo'd symbol
    is caught immediately rather than becoming a permanent error card.
    """
    from database import add_etoro_holding

    validation = watchlist_analysis.validate_symbol(body.symbol)
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation["error"] or "Invalid symbol")

    symbol = validation.get("resolved_symbol") or body.symbol.strip().upper()
    name = body.name or validation["name"] or symbol

    holding_id = add_etoro_holding(symbol, name, body.quantity, body.entry_price, body.notes)
    return {"status": "ok", "id": holding_id, "symbol": symbol, "name": name}


class EtoroHoldingUpdateRequest(BaseModel):
    quantity: float = None
    entry_price: float = None
    notes: str = None


@app.put("/api/etoro/holdings/{holding_id}")
def etoro_update_holding(holding_id: int, body: EtoroHoldingUpdateRequest):
    """Update quantity/entry price/notes for an existing eToro holding
    (e.g. after averaging up/down, or correcting a typo)."""
    from database import update_etoro_holding

    updated = update_etoro_holding(holding_id, body.quantity, body.entry_price, body.notes)
    if not updated:
        raise HTTPException(status_code=404, detail=f"No eToro holding with id {holding_id}")
    return {"status": "ok", "id": holding_id}


@app.delete("/api/etoro/holdings/{holding_id}")
def etoro_remove_holding(holding_id: int):
    """Remove an eToro holding from your manually-tracked portfolio."""
    from database import delete_etoro_holding

    delete_etoro_holding(holding_id)
    return {"status": "ok", "removed_id": holding_id}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
