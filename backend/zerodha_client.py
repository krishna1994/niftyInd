"""
Zerodha Kite Connect integration.

This module provides a thin, safe wrapper around the official `kiteconnect`
SDK for connecting this app to a real Zerodha trading account. It is
designed so the app works perfectly WITHOUT any Zerodha credentials
configured (all endpoints gracefully report "not configured" instead of
crashing) — you can wire up your API key/secret at any time later purely
via environment variables, with zero code changes required.

## How to enable Zerodha integration (when you have your API key)

1. Get API credentials from https://developers.kite.trade/ (requires an
   active Zerodha trading account + a one-time ~₹2000/month Kite Connect
   API subscription).
2. Create a `.env` file in the `backend/` directory (copy `.env.example`)
   and fill in:

       ZERODHA_API_KEY=your_api_key_here
       ZERODHA_API_SECRET=your_api_secret_here

   (ZERODHA_ACCESS_TOKEN is filled in automatically after you complete the
   login flow below — you don't need to set it manually.)

3. Restart the backend. Go to Settings → Zerodha Integration in the UI and
   click "Connect to Zerodha". You'll be redirected to Zerodha's login
   page; after logging in you're redirected back to this app with a
   `request_token`, which the backend automatically exchanges for a
   long-lived (until next day 6am IST) `access_token`.
4. Once connected, live positions/holdings/margins/order-placement become
   available throughout the app.

## Why this design

Kite Connect's access tokens expire daily (Zerodha's security policy), so
there is no way to have a "permanent" API key that works forever without
a login step — this is standard for ALL Kite Connect integrations, not a
limitation of this app. The access token is cached in the local SQLite DB
so you only need to re-login once per trading day (typically each morning).
"""
import os
import logging
from datetime import datetime, date
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

try:
    from kiteconnect import KiteConnect
    KITECONNECT_AVAILABLE = True
except ImportError:
    KITECONNECT_AVAILABLE = False
    KiteConnect = None

from database import get_setting, set_setting
from broker_base import BaseBroker

# ── Broker Implementation ──────────────────────────────────────────────────

class ZerodhaBroker(BaseBroker):
    """
    Implementation of BaseBroker for Zerodha Kite Connect.
    Wraps the KiteConnect SDK to provide a standardized interface.
    """
    def get_connection_status(self) -> Dict[str, Any]:
        return get_connection_status()

    def get_profile(self) -> Dict[str, Any]:
        return get_profile()

    def get_margins(self) -> Dict[str, Any]:
        return get_margins()

    def get_positions(self) -> List[Dict[str, Any]]:
        # Kite returns {"net": [...], "day": [...]}
        # "net" = end-of-day net positions (what we want for portfolio view)
        pos = get_positions()
        if isinstance(pos, dict):
            return pos.get("net", [])
        if isinstance(pos, list):
            return pos
        return []

    def get_holdings(self) -> List[Dict[str, Any]]:
        return get_holdings()

    def place_order(self, order_details: Dict[str, Any]) -> Dict[str, Any]:
        # Map standardized order_details to Zerodha's place_order parameters
        return place_order(
            tradingsymbol=order_details["tradingsymbol"],
            exchange=order_details.get("exchange", "NFO"),
            transaction_type=order_details["transaction_type"],
            quantity=order_details["quantity"],
            order_type=order_details.get("order_type", "MARKET"),
            product=order_details.get("product", "MIS"),
            price=order_details.get("price"),
            trigger_price=order_details.get("trigger_price"),
            variety=order_details.get("variety", "regular")
        )

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        return cancel_order(order_id)

    def get_quote(self, symbols: List[str]) -> Dict[str, Any]:
        return get_quote(symbols)

    def get_option_chain(self, symbol: str) -> Dict[str, Any]:
        """
        Fetches the option chain for the given symbol.
        For NIFTY, it uses the nse_options module.
        """
        from nse_options import get_nse_options_data
        if symbol.upper() == "NIFTY":
            return get_nse_options_data()
        raise NotImplementedError(f"Option chain for {symbol} not implemented yet.")

# ── Configuration (env-driven; nothing hardcoded) ──────────────────────────

def get_api_key() -> Optional[str]:
    return os.environ.get("ZERODHA_API_KEY", "").strip() or None


def get_api_secret() -> Optional[str]:
    return os.environ.get("ZERODHA_API_SECRET", "").strip() or None


def is_configured() -> bool:
    """True if the operator has supplied API key + secret via env vars."""
    return KITECONNECT_AVAILABLE and bool(get_api_key()) and bool(get_api_secret())


# ── Access token persistence (survives server restarts within the same day) ─

_ACCESS_TOKEN_SETTING_KEY = "zerodha_access_token"
_ACCESS_TOKEN_DATE_SETTING_KEY = "zerodha_access_token_date"


def _load_cached_access_token() -> Optional[str]:
    """
    Kite access tokens are valid until ~6am IST the NEXT day. We store the
    token + the date it was issued in the local DB; if the stored date
    isn't today, we treat it as expired (safer than trusting an old token
    and getting confusing 403s deep in a request).
    """
    token = get_setting(_ACCESS_TOKEN_SETTING_KEY)
    issued_date = get_setting(_ACCESS_TOKEN_DATE_SETTING_KEY)
    if not token or not issued_date:
        return None
    if issued_date != date.today().isoformat():
        return None
    return token


def _save_access_token(token: str):
    set_setting(_ACCESS_TOKEN_SETTING_KEY, token)
    set_setting(_ACCESS_TOKEN_DATE_SETTING_KEY, date.today().isoformat())


def clear_access_token():
    set_setting(_ACCESS_TOKEN_SETTING_KEY, "")
    set_setting(_ACCESS_TOKEN_DATE_SETTING_KEY, "")


def start_auto_reconnect_background_loop():
    """
    If auto-login credentials are remembered (see /api/zerodha/auto-login in
    main.py), periodically checks whether the Zerodha session has expired
    (tokens expire daily ~6am IST) and automatically re-logs-in using the
    saved user ID/password/TOTP secret — so you never have to manually
    reconnect each morning. Fully inert (does nothing) if no credentials are
    remembered. Runs in a daemon thread; checks every 30 minutes.
    """
    import threading
    import time as _time

    def _loop():
        while True:
            try:
                enabled = get_setting("zerodha_autologin_enabled") == "true"
                if enabled and not get_connection_status().get("connected"):
                    user_id = get_setting("zerodha_autologin_user_id")
                    password = get_setting("zerodha_autologin_password")
                    totp_secret = get_setting("zerodha_autologin_totp_secret")
                    api_key = get_api_key()
                    if user_id and password and totp_secret and api_key:
                        import zerodha_autologin
                        logger.info("zerodha_client: session expired, attempting auto-reconnect...")
                        request_token = zerodha_autologin.auto_login_and_get_request_token(
                            user_id=user_id, password=password,
                            totp_secret=totp_secret, api_key=api_key,
                        )
                        complete_login(request_token)
                        logger.info("zerodha_client: auto-reconnect succeeded.")
            except Exception as e:
                logger.warning(f"zerodha_client: auto-reconnect attempt failed: {e}")
            _time.sleep(30 * 60)

    threading.Thread(target=_loop, daemon=True).start()
    logger.info("zerodha_client: auto-reconnect background loop started (checks every 30 min)")


# ── Kite client singleton ───────────────────────────────────────────────────

_kite_instance = None
_kite_access_token = None


def get_kite() -> "KiteConnect":
    """
    Returns an authenticated KiteConnect instance, or raises RuntimeError
    with a clear, actionable message if not configured/authenticated yet.
    Callers (API endpoints) should catch this and return a friendly 4xx.
    """
    global _kite_instance, _kite_access_token

    if not KITECONNECT_AVAILABLE:
        raise RuntimeError(
            "kiteconnect package not installed. Run: pip install kiteconnect"
        )

    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "Zerodha not configured. Set ZERODHA_API_KEY and ZERODHA_API_SECRET "
            "in backend/.env, then connect via Settings → Zerodha Integration."
        )

    token = _load_cached_access_token()
    if not token:
        raise RuntimeError(
            "Zerodha not connected (or session expired — tokens expire daily "
            "around 6am IST). Please reconnect via Settings → Zerodha Integration."
        )

    if _kite_instance is None or _kite_access_token != token:
        _kite_instance = KiteConnect(api_key=api_key)
        _kite_instance.set_access_token(token)
        _kite_access_token = token

    return _kite_instance


def get_login_url() -> str:
    """Returns the Zerodha Kite login URL to redirect the user to."""
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "Zerodha not configured. Set ZERODHA_API_KEY and ZERODHA_API_SECRET "
            "in backend/.env first."
        )
    kite = KiteConnect(api_key=api_key)
    return kite.login_url()


def complete_login(request_token: str) -> dict:
    """
    Exchange the request_token (received via the login redirect callback)
    for a long-lived access_token, then cache it. Returns basic profile info
    on success so the caller can confirm which account is connected.
    """
    api_key = get_api_key()
    api_secret = get_api_secret()
    if not api_key or not api_secret:
        raise RuntimeError("Zerodha not configured (missing API key/secret).")

    kite = KiteConnect(api_key=api_key)
    data = kite.generate_session(request_token, api_secret=api_secret)
    access_token = data["access_token"]
    _save_access_token(access_token)

    kite.set_access_token(access_token)
    global _kite_instance, _kite_access_token
    _kite_instance = kite
    _kite_access_token = access_token

    profile = kite.profile()
    return {
        "user_id": profile.get("user_id"),
        "user_name": profile.get("user_name"),
        "email": profile.get("email"),
        "broker": profile.get("broker"),
    }


def get_connection_status() -> dict:
    """
    Non-throwing status check, safe to call anytime (e.g. to render a
    connection badge in the UI). Never raises.
    """
    if not KITECONNECT_AVAILABLE:
        return {
            "installed": False,
            "configured": False,
            "connected": False,
            "message": "kiteconnect package not installed on the server.",
        }

    configured = is_configured()
    if not configured:
        return {
            "installed": True,
            "configured": False,
            "connected": False,
            "message": (
                "Zerodha API key/secret not set. Add ZERODHA_API_KEY and "
                "ZERODHA_API_SECRET to backend/.env to enable this integration."
            ),
        }

    token = _load_cached_access_token()
    if not token:
        return {
            "installed": True,
            "configured": True,
            "connected": False,
            "message": "Configured but not connected. Click 'Connect to Zerodha' to log in.",
        }

    # We have a token — verify it's actually still valid with a lightweight call.
    try:
        kite = get_kite()
        profile = kite.profile()
        return {
            "installed": True,
            "configured": True,
            "connected": True,
            "message": "Connected.",
            "user_id": profile.get("user_id"),
            "user_name": profile.get("user_name"),
            "broker": profile.get("broker"),
        }
    except Exception as e:
        logger.warning(f"Zerodha token validation failed: {e}")
        return {
            "installed": True,
            "configured": True,
            "connected": False,
            "message": f"Session expired or invalid ({e}). Please reconnect.",
        }


# ── Data access helpers (all raise RuntimeError with clear messages if not connected) ──

def get_profile() -> dict:
    return get_kite().profile()


def get_margins() -> dict:
    return get_kite().margins()


def get_positions() -> dict:
    return get_kite().positions()


def get_holdings() -> list:
    return get_kite().holdings()


def get_orders() -> list:
    return get_kite().orders()


def get_trades() -> list:
    """
    Returns today's executed trades (fills). Different from orders — an order
    can have multiple partial fills, each of which appears as a separate trade.
    Useful for the auto-trader audit trail and the Settings → Orders view.
    """
    return get_kite().trades()


def get_order_history(order_id: str) -> list:
    """Returns the full state history of a single order (placed → open → complete)."""
    return get_kite().order_history(order_id)


def get_gtts() -> list:
    """
    Returns all active GTT (Good Till Triggered) orders on the account.
    The auto-trader places a GTT OCO exit alongside every entry — this lets
    the UI show and manage those pending exits.
    """
    return get_kite().get_gtts()


def get_gtt(trigger_id: int) -> dict:
    """Returns a single GTT order by its trigger ID."""
    return get_kite().get_gtt(trigger_id)


def delete_gtt(trigger_id: int) -> dict:
    """
    Cancels/deletes a GTT order. Used when manually closing a position that
    has an associated auto-trader GTT exit — the GTT must be cancelled too,
    otherwise it will fire on a position that no longer exists.
    """
    result = get_kite().delete_gtt(trigger_id)
    return {"trigger_id": result}


def modify_order(
    order_id: str,
    quantity: int = None,
    price: float = None,
    trigger_price: float = None,
    order_type: str = None,
    variety: str = "regular",
) -> dict:
    """
    Modifies an open (pending) order — e.g. change a limit price or quantity.
    Only works on orders that haven't been filled yet.
    """
    kite = get_kite()
    kwargs = {"variety": variety, "order_id": order_id}
    if quantity is not None:
        kwargs["quantity"] = quantity
    if price is not None:
        kwargs["price"] = price
    if trigger_price is not None:
        kwargs["trigger_price"] = trigger_price
    if order_type is not None:
        kwargs["order_type"] = order_type
    result = kite.modify_order(**kwargs)
    return {"order_id": result}


def convert_position(
    tradingsymbol: str,
    exchange: str,
    transaction_type: str,
    position_type: str,
    quantity: int,
    old_product: str,
    new_product: str,
) -> bool:
    """
    Converts a position from one product type to another (e.g. MIS → NRML to
    carry an intraday F&O position overnight). Returns True on success.
    """
    return get_kite().convert_position(
        exchange=exchange,
        tradingsymbol=tradingsymbol,
        transaction_type=transaction_type,
        position_type=position_type,
        quantity=quantity,
        old_product=old_product,
        new_product=new_product,
    )


def get_ltp(instruments: list) -> dict:
    """
    instruments: list of "exchange:tradingsymbol" strings,
    e.g. ["NSE:NIFTY 50", "NFO:NIFTY24DEC24200CE"]
    """
    return get_kite().ltp(instruments)


def get_quote(instruments: list) -> dict:
    return get_kite().quote(instruments)


def place_order(
    tradingsymbol: str,
    exchange: str,
    transaction_type: str,
    quantity: int,
    order_type: str = "MARKET",
    product: str = "MIS",
    price: Optional[float] = None,
    trigger_price: Optional[float] = None,
    variety: str = "regular",
) -> dict:
    """
    Places a real order on Zerodha. USE WITH EXTREME CAUTION — this places
    an actual live order with real money once Zerodha integration is
    connected. There is no simulation/paper-trading mode for this function;
    for risk-free testing use the app's existing "Dry Run" feature instead.

    transaction_type: "BUY" or "SELL"
    order_type: "MARKET", "LIMIT", "SL", "SL-M"
    product: "MIS" (intraday), "NRML" (carry-forward, for F&O), "CNC" (equity delivery)
    """
    kite = get_kite()
    kwargs = dict(
        variety=variety,
        exchange=exchange,
        tradingsymbol=tradingsymbol,
        transaction_type=transaction_type,
        quantity=quantity,
        order_type=order_type,
        product=product,
    )
    if price is not None:
        kwargs["price"] = price
    if trigger_price is not None:
        kwargs["trigger_price"] = trigger_price

    order_id = kite.place_order(**kwargs)
    return {"order_id": order_id}


def cancel_order(order_id: str, variety: str = "regular") -> dict:
    kite = get_kite()
    result = kite.cancel_order(variety=variety, order_id=order_id)
    return {"order_id": result}


def get_historical_data(
    instrument_token: int,
    from_date: str,
    to_date: str,
    interval: str = "day",
) -> list:
    """
    interval: "minute", "3minute", "5minute", "10minute", "15minute",
              "30minute", "60minute", "day"
    """
    kite = get_kite()
    return kite.historical_data(instrument_token, from_date, to_date, interval)


# ── Instrument lookup (for auto_trader.py) ──────────────────────────────────
# We NEVER hand-construct Zerodha trading symbols (e.g. "NIFTY24DEC24200CE")
# manually — that's fragile and a wrong-symbol order with real money is an
# unacceptable risk. Instead we look up the exact tradingsymbol + instrument
# token from Kite's own authoritative instruments list for the requested
# strike/expiry/type, and only proceed if we find an EXACT match.

_nfo_instruments_cache = {"data": None, "fetched_at": 0}
_NFO_CACHE_TTL_SECONDS = 6 * 60 * 60  # instrument list changes rarely intraday


def _get_nfo_instruments():
    """Cached fetch of the full NFO instrument list (thousands of rows)."""
    import time
    now = time.time()
    if (
        _nfo_instruments_cache["data"] is not None
        and now - _nfo_instruments_cache["fetched_at"] < _NFO_CACHE_TTL_SECONDS
    ):
        return _nfo_instruments_cache["data"]

    kite = get_kite()
    instruments = kite.instruments("NFO")
    _nfo_instruments_cache["data"] = instruments
    _nfo_instruments_cache["fetched_at"] = now
    return instruments


def find_nifty_option_symbol(strike: int, expiry_date: str, option_type: str) -> dict:
    """
    Look up the exact Zerodha tradingsymbol for a NIFTY index option.

    strike: e.g. 24200
    expiry_date: "YYYY-MM-DD" (e.g. "2026-09-04") — must match Kite's exact
                 expiry date for that contract (usually a Thursday for weekly
                 NIFTY options).
    option_type: "CE" or "PE"

    Returns {"tradingsymbol": ..., "instrument_token": ..., "lot_size": ...,
             "expiry": ...} on an exact match.

    Raises RuntimeError if no exact match is found — this is intentional:
    we would rather fail loudly and skip the trade than guess and risk
    placing an order on the wrong contract.
    """
    from datetime import datetime as _dt

    instruments = _get_nfo_instruments()
    target_expiry = _dt.strptime(expiry_date, "%Y-%m-%d").date()

    matches = [
        inst
        for inst in instruments
        if inst.get("name") == "NIFTY"
        and inst.get("instrument_type") == option_type
        and inst.get("strike") == float(strike)
        and inst.get("expiry") == target_expiry
    ]

    if not matches:
        raise RuntimeError(
            f"No exact Zerodha NIFTY {option_type} contract found for strike="
            f"{strike}, expiry={expiry_date}. Refusing to guess a trading "
            f"symbol — auto-trader will skip this signal."
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"Ambiguous match ({len(matches)} contracts) for NIFTY {option_type} "
            f"strike={strike}, expiry={expiry_date} — refusing to proceed."
        )

    inst = matches[0]
    return {
        "tradingsymbol": inst["tradingsymbol"],
        "instrument_token": inst["instrument_token"],
        "lot_size": inst["lot_size"],
        "expiry": str(inst["expiry"]),
    }


def get_nifty_lot_size() -> int:
    """
    Returns the CURRENT NIFTY options lot size, fetched live from Kite's own
    instruments list (never hand-coded/hardcoded) — NSE periodically revises
    the lot size (e.g. 50 → 75 in 2025), so this always reflects the truth
    rather than a value that can silently go stale in source code.
    Falls back to 75 (the lot size at the time this was written) ONLY if
    Zerodha isn't connected — callers should treat that fallback as
    approximate and prefer to have Zerodha connected for accuracy.
    """
    try:
        instruments = _get_nfo_instruments()
        nifty_opts = [i for i in instruments if i.get("name") == "NIFTY" and i.get("instrument_type") in ("CE", "PE")]
        if nifty_opts:
            return int(nifty_opts[0]["lot_size"])
    except Exception as e:
        logger.warning(f"Could not fetch live NIFTY lot size, using fallback: {e}")
    return 75


def estimate_order_margin(orders: list) -> dict:
    """
    Estimates the margin (capital) required to place a multi-leg order,
    using Kite's own pre-trade margin calculator (`basket_order_margins`) —
    this accounts for cross-margining benefits between legs (e.g. a short
    call + long call hedge requires LESS margin together than either alone),
    which is exactly why iron condors are capital-efficient vs naked shorts.

    orders: list of dicts, each with keys: exchange, tradingsymbol,
            transaction_type, variety, product, order_type, quantity, price
    Returns {"total_margin": float, "raw": <full Kite response>} or raises
    RuntimeError with a clear message if the call fails (e.g. not connected).
    """
    kite = get_kite()
    try:
        result = kite.basket_order_margins(orders, consider_positions=True)
        total = result.get("final", {}).get("total", None)
        if total is None:
            # Older/alternate response shape: sum each leg's margin directly
            total = sum(leg.get("total", 0) for leg in result.get("orders", []))
        return {"total_margin": float(total), "raw": result}
    except Exception as e:
        raise RuntimeError(f"Could not estimate order margin: {e}")


def get_available_balance() -> dict:
    """
    Returns available cash/margin balance across segments (equity + F&O),
    from Kite's live margins() call. Returns the F&O ("commodity"/"equity"
    depending on segment structure) available balance most relevant for
    NIFTY index options — specifically the 'equity' segment's 'available'
    cash, which is what NIFTY index F&O margin is drawn from.
    """
    margins = get_margins()
    equity = margins.get("equity", {})
    available = equity.get("available", {})
    return {
        "available_cash": available.get("live_balance", available.get("cash", 0)),
        "available_margin": available.get("net", 0),
        "used_margin": equity.get("utilised", {}).get("debits", 0),
        "raw": margins,
    }


def place_gtt_oco_exit(
    tradingsymbol: str,
    exchange: str,
    quantity: int,
    last_price: float,
    stop_loss_price: float,
    target_price: float,
) -> dict:
    """
    Places a GTT (Good Till Triggered) One-Cancels-Other order that will
    automatically SELL (exit) the position if EITHER the stop-loss OR the
    target price is hit — whichever comes first cancels the other. This is
    how we attach automatic risk management to an auto-placed entry order
    without needing to poll prices ourselves.
    """
    kite = get_kite()
    gtt_id = kite.place_gtt(
        trigger_type=kite.GTT_TYPE_OCO,
        tradingsymbol=tradingsymbol,
        exchange=exchange,
        trigger_values=[stop_loss_price, target_price],
        last_price=last_price,
        orders=[
            {
                "transaction_type": "SELL",
                "quantity": quantity,
                "order_type": "LIMIT",
                "product": "MIS",
                "price": stop_loss_price,
            },
            {
                "transaction_type": "SELL",
                "quantity": quantity,
                "order_type": "LIMIT",
                "product": "MIS",
                "price": target_price,
            },
        ],
    )
    return {"gtt_id": gtt_id}