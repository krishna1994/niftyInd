"""
Fully automated Zerodha login (user ID + password + TOTP secret) — no manual
browser step required.

╔══════════════════════════════════════════════════════════════════════════╗
║  IMPORTANT: HOW THIS WORKS AND WHY IT'S DIFFERENT FROM THE OFFICIAL FLOW  ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Zerodha's OFFICIAL Kite Connect API does NOT support username/password  ║
║  login — this is a deliberate SEBI-mandated security requirement (all    ║
║  broker APIs must require 2FA via a browser-based login). There is no    ║
║  way to bypass this through the official API.                            ║
║                                                                            ║
║  This module instead automates Zerodha's actual LOGIN WEBSITE (the same  ║
║  pages you'd visit manually) by directly calling the same internal HTTP  ║
║  endpoints your browser calls when you type your password and TOTP code.║
║  This is a well-known pattern used across the Indian algo-trading        ║
║  community (search "kite auto login totp" — many public gists do this   ║
║  exact thing). It still goes through 2FA — just automatically, using a   ║
║  TOTP secret instead of you typing a 6-digit code each morning.          ║
║                                                                            ║
║  RISKS you should know before using this:                                ║
║    - This uses UNDOCUMENTED, UNOFFICIAL endpoints. Zerodha can change    ║
║      them at any time without notice, breaking this feature (the manual  ║
║      OAuth flow in zerodha_client.py will keep working regardless).      ║
║    - Storing your account password (even encrypted-at-rest) is a larger  ║
║      attack surface than storing only an API key. Only use this if       ║
║      you're comfortable with that tradeoff on your own machine.          ║
║    - Your TOTP SECRET (not the 6-digit code) is required — find it in    ║
║      your authenticator app's setup screen when you first enabled 2FA,   ║
║      or by re-scanning the QR code from Zerodha's 2FA settings page.     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import logging
import re
from urllib.parse import urlparse, parse_qs

import requests

try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False

logger = logging.getLogger(__name__)

KITE_LOGIN_URL = "https://kite.zerodha.com/api/login"
KITE_TWOFA_URL = "https://kite.zerodha.com/api/twofa"
KITE_CONNECT_LOGIN_URL = "https://kite.zerodha.com/connect/login"


def is_available() -> bool:
    return PYOTP_AVAILABLE


def auto_login_and_get_request_token(
    user_id: str,
    password: str,
    totp_secret: str,
    api_key: str,
) -> str:
    """
    Fully automates the Zerodha login flow (password + TOTP) and returns the
    request_token that would normally require a manual browser round-trip.

    Raises RuntimeError with a clear message on any failure (wrong password,
    wrong TOTP secret, Zerodha changed their internal endpoints, etc.) —
    never silently returns a bad token.
    """
    if not PYOTP_AVAILABLE:
        raise RuntimeError(
            "pyotp package not installed. Run: pip install pyotp"
        )

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    # Step 1: username + password
    resp = session.post(
        KITE_LOGIN_URL,
        data={"user_id": user_id, "password": password},
        headers=headers,
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Login step 1 failed (HTTP {resp.status_code}) — check user ID/password.")
    data = resp.json()
    if data.get("status") != "success":
        raise RuntimeError(f"Login step 1 rejected: {data.get('message', 'unknown error')}")

    request_id = data["data"]["request_id"]

    # Step 2: TOTP-based 2FA
    try:
        totp_code = pyotp.TOTP(totp_secret).now()
    except Exception as e:
        raise RuntimeError(f"Could not generate TOTP code from the provided secret: {e}")

    resp = session.post(
        KITE_TWOFA_URL,
        data={
            "user_id": user_id,
            "request_id": request_id,
            "twofa_value": totp_code,
            "twofa_type": "totp",
        },
        headers=headers,
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"2FA step failed (HTTP {resp.status_code}) — check your TOTP secret.")
    data = resp.json()
    if data.get("status") != "success":
        raise RuntimeError(
            f"2FA rejected: {data.get('message', 'unknown error')} — "
            f"double-check the TOTP secret is correct (it's the SECRET KEY, not the 6-digit code)."
        )

    # Step 3: now that the session is authenticated (cookies set), hit the
    # Kite Connect authorize URL for our API key — Zerodha will redirect us
    # (since we're now logged in) straight to our app's redirect URL with
    # ?request_token=... appended. We just need to capture that redirect
    # without actually following it to our (possibly-unreachable) redirect URL.
    resp = session.get(
        KITE_CONNECT_LOGIN_URL,
        params={"api_key": api_key, "v": "3"},
        headers=headers,
        timeout=15,
        allow_redirects=True,
    )

    # The request_token appears as a query param on the FINAL redirected URL
    # (our own Redirect URL, which may not even resolve — that's fine, we
    # only care about the URL itself, not its response).
    final_url = resp.url
    parsed = urlparse(final_url)
    qs = parse_qs(parsed.query)
    request_token = qs.get("request_token", [None])[0]

    if not request_token:
        # Sometimes Zerodha shows an intermediate "authorize this app" page
        # instead of auto-redirecting (e.g. first-time authorization for this
        # api_key). Try to find a request_token anywhere in the response body
        # as a fallback, otherwise fail clearly.
        match = re.search(r"request_token=([a-zA-Z0-9]+)", resp.text)
        if match:
            request_token = match.group(1)
        else:
            raise RuntimeError(
                "Logged in successfully, but could not extract a request_token from "
                "the redirect. This usually means Zerodha changed their internal login "
                "flow — the manual 'Connect to Zerodha' button will still work as a fallback."
            )

    return request_token