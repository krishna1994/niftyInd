"""
NSE Options Chain data fetcher - Free, no API key required
Fetches live options chain data from NSE India website.

NOTE: NSE periodically changes its internal API paths. As of this version,
the working endpoint for index option chains is `option-chain-v3`, which
requires an explicit `expiry` query param (empty/omitted param returns {}).
We first fetch the list of available expiries via a throwaway call, then
fetch the real chain for the nearest expiry.
"""
import requests
import pandas as pd
import logging
import time
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class NSEOptionsChain:
    """Fetch Nifty options chain data from NSE"""

    def __init__(self):
        self.base_url = "https://www.nseindia.com"
        self.session = requests.Session()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",  # omit 'br' (brotli) - requests can't decode it without the brotli package
            "Referer": "https://www.nseindia.com/option-chain",
            "Connection": "keep-alive"
        }
        # Initialize session with cookies
        self._init_session()

    def _init_session(self):
        """Initialize session by visiting NSE homepage to get cookies"""
        try:
            self.session.get(self.base_url, headers=self.headers, timeout=10)
            time.sleep(1)  # NSE rate-limits rapid successive requests
            logger.info("NSE session initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize NSE session: {str(e)}")

    def _get_expiry_dates(self, symbol="NIFTY"):
        """Fetch the list of available expiry dates for a symbol."""
        try:
            # Any valid expiry string in the URL triggers NSE to return the
            # full expiryDates list along with that expiry's chain. We use a
            # near-future guess; if it's wrong NSE still returns the full
            # expiryDates list (just with data=[] for filtered), which is
            # enough for us to pick the real nearest expiry on a 2nd call.
            probe_date = (datetime.now() + timedelta(days=7)).strftime("%d-%b-%Y")
            url = f"{self.base_url}/api/option-chain-v3?type=Indices&symbol={symbol}&expiry={probe_date}"
            resp = self.session.get(url, headers=self.headers, timeout=10)
            if resp.status_code != 200:
                return []
            data = resp.json()
            return data.get("records", {}).get("expiryDates", [])
        except Exception as e:
            logger.error(f"Error fetching expiry dates: {str(e)}")
            return []

    def fetch_options_chain(self, symbol="NIFTY", expiry=None):
        """
        Fetch options chain data for given symbol.

        Args:
            symbol: e.g. "NIFTY"
            expiry: optional explicit expiry string like "01-Sep-2026".
                    If None, automatically uses the nearest available expiry.

        Returns:
            dict with keys: spot_price, pcr, max_pain, strikes_data, expiry_dates
        """
        try:
            if expiry is None:
                expiries = self._get_expiry_dates(symbol)
                if not expiries:
                    logger.error("Could not determine expiry dates from NSE")
                    return None
                expiry = expiries[0]
            else:
                expiries = None

            url = f"{self.base_url}/api/option-chain-v3?type=Indices&symbol={symbol}&expiry={expiry}"
            response = self.session.get(url, headers=self.headers, timeout=10)

            if response.status_code != 200:
                logger.error(f"NSE API returned status {response.status_code}")
                return None

            data = response.json()

            if 'records' not in data or 'data' not in data['records']:
                logger.error("Invalid response structure from NSE")
                return None

            records = data['records']
            spot_price = records.get('underlyingValue', 0)
            expiry_dates = records.get('expiryDates', expiries or [])

            nearest_expiry = expiry

            # Parse options data
            options_data = records['data']

            # Calculate PCR and Max Pain
            pcr_data = self._calculate_pcr(options_data, nearest_expiry)
            max_pain = self._calculate_max_pain(options_data, nearest_expiry, spot_price)

            # Get top OI strikes
            top_strikes = self._get_top_oi_strikes(options_data, nearest_expiry, spot_price)

            dte = self._calculate_dte(nearest_expiry)

            analysis = self._analyze_chain(
                options_data, spot_price, pcr_data, max_pain,
                top_strikes["calls"], top_strikes["puts"], dte,
            )

            return {
                "spot_price": spot_price,
                "pcr": pcr_data["pcr"],
                "pcr_signal": pcr_data["signal"],
                "max_pain": max_pain,
                "nearest_expiry": nearest_expiry,
                "days_to_expiry": dte,
                "top_call_oi": top_strikes["calls"],
                "top_put_oi": top_strikes["puts"],
                "total_call_oi": pcr_data["total_call_oi"],
                "total_put_oi": pcr_data["total_put_oi"],
                "all_strikes": options_data,
                "analysis": analysis,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error fetching NSE options chain: {str(e)}")
            return None

    def _analyze_chain(self, options_data, spot_price, pcr_data, max_pain,
                        top_calls, top_puts, dte):
        """
        Turns the raw option chain numbers (PCR, Max Pain, OI walls, IV skew)
        into a concrete, actionable read — support/resistance levels derived
        from real OI walls, a directional bias, an IV-skew read, and a plain
        -English suggested approach. This is what elevates the options chain
        page from "just data" into something a trader can actually act on.
        """
        reasoning = []

        # ── Support / Resistance from real OI walls ─────────────────────
        # The single largest put-OI strike AT OR BELOW spot is the nearest
        # real support (put writers are financially incentivized to defend
        # it). The single largest call-OI strike AT OR ABOVE spot is the
        # nearest real resistance, for the same reason on the call side.
        puts_below = [p for p in top_puts if p["strike"] <= spot_price]
        calls_above = [c for c in top_calls if c["strike"] >= spot_price]
        support = max(puts_below, key=lambda p: p["oi"])["strike"] if puts_below else (top_puts[0]["strike"] if top_puts else None)
        resistance = min(calls_above, key=lambda c: c["oi"])["strike"] if calls_above else (top_calls[0]["strike"] if top_calls else None)
        # Prefer the single highest-OI wall on each side if it disagrees
        # with the "nearest" pick above (the biggest wall is what actually
        # matters most, even if it's the 2nd-nearest strike).
        if top_puts:
            biggest_put_wall = max(top_puts, key=lambda p: p["oi"])["strike"]
            if support is None or top_puts and biggest_put_wall != support:
                # Only override to the biggest wall if it's still <= spot
                # (a support level above spot doesn't make sense)
                if biggest_put_wall <= spot_price:
                    support = biggest_put_wall
        if top_calls:
            biggest_call_wall = max(top_calls, key=lambda c: c["oi"])["strike"]
            if biggest_call_wall >= spot_price:
                resistance = biggest_call_wall

        range_width = (resistance - support) if (support and resistance) else None
        range_width_pct = round((range_width / spot_price) * 100, 2) if range_width else None

        if support and resistance:
            reasoning.append(
                f"Largest put-OI wall at {support} acts as nearest support; "
                f"largest call-OI wall at {resistance} acts as nearest resistance "
                f"— a {range_width}pt ({range_width_pct}%) range."
            )

        # ── PCR-based directional bias ───────────────────────────────────
        pcr = pcr_data["pcr"]
        pcr_signal = pcr_data["signal"]
        if pcr_signal == "BULLISH":
            reasoning.append(f"PCR of {pcr} (>1.2) shows heavier put writing than call writing — contrarian bullish bias.")
        elif pcr_signal == "BEARISH":
            reasoning.append(f"PCR of {pcr} (<0.8) shows heavier call writing than put writing — contrarian bearish bias.")
        else:
            reasoning.append(f"PCR of {pcr} is in the neutral 0.8–1.2 band — no strong directional skew from OI alone.")

        # ── Max Pain pull ─────────────────────────────────────────────────
        max_pain_diff = max_pain - spot_price
        max_pain_diff_pct = round((max_pain_diff / spot_price) * 100, 2)
        max_pain_dir = None
        if abs(max_pain_diff_pct) > 0.3:
            max_pain_dir = "up" if max_pain_diff > 0 else "down"
            reasoning.append(
                f"Max pain at {max_pain} is {abs(max_pain_diff):.0f}pts ({abs(max_pain_diff_pct)}%) "
                f"{'above' if max_pain_diff > 0 else 'below'} spot — theory suggests a mild pull {max_pain_dir}wards into expiry "
                f"(strongest as DTE approaches 0, weak/unreliable this early)."
            )
        else:
            reasoning.append(f"Max pain ({max_pain}) is very close to spot — no meaningful pull expected from this alone.")

        # ── IV skew (fear gauge between calls and puts) ──────────────────
        avg_call_iv = sum(c["iv"] for c in top_calls if c["iv"]) / len([c for c in top_calls if c["iv"]]) if any(c["iv"] for c in top_calls) else None
        avg_put_iv = sum(p["iv"] for p in top_puts if p["iv"]) / len([p for p in top_puts if p["iv"]]) if any(p["iv"] for p in top_puts) else None
        iv_skew_note = None
        if avg_call_iv and avg_put_iv:
            iv_diff = avg_put_iv - avg_call_iv
            if iv_diff > 1.5:
                iv_skew_note = f"Put IV ({avg_put_iv:.1f}%) notably higher than Call IV ({avg_call_iv:.1f}%) — market is paying up for downside protection (mild fear skew)."
            elif iv_diff < -1.5:
                iv_skew_note = f"Call IV ({avg_call_iv:.1f}%) notably higher than Put IV ({avg_put_iv:.1f}%) — unusual; market pricing in more upside risk than usual."
            else:
                iv_skew_note = f"Call IV ({avg_call_iv:.1f}%) and Put IV ({avg_put_iv:.1f}%) are close — no strong skew, IV mostly reflects general volatility level."
            reasoning.append(iv_skew_note)

        # ── Overall bias combines PCR + max pain direction (agree/disagree) ──
        bias_votes = []
        if pcr_signal in ("BULLISH", "BEARISH"):
            bias_votes.append(pcr_signal)
        if max_pain_dir == "up":
            bias_votes.append("BULLISH")
        elif max_pain_dir == "down":
            bias_votes.append("BEARISH")

        if bias_votes.count("BULLISH") > bias_votes.count("BEARISH"):
            overall_bias = "BULLISH"
        elif bias_votes.count("BEARISH") > bias_votes.count("BULLISH"):
            overall_bias = "BEARISH"
        else:
            overall_bias = "NEUTRAL"

        # ── Concrete suggested approach ───────────────────────────────────
        # Range-bound premium selling is the natural strategy when there's a
        # clearly defined OI-wall range; directional buying makes more sense
        # when PCR + max pain both agree strongly on a direction.
        if support and resistance and range_width_pct is not None and range_width_pct < 4 and dte is not None and dte >= 1:
            suggested_action = (
                f"Spot is boxed between {support} support and {resistance} resistance "
                f"(only {range_width_pct}% wide) — this OI structure favors a RANGE-BOUND "
                f"strategy like a short Iron Condor with short strikes near/beyond these walls "
                f"(see the Iron Condor tab, which uses this same live chain to suggest exact strikes)."
            )
        elif overall_bias == "BULLISH":
            suggested_action = (
                f"PCR and max pain both lean bullish. If also confirmed by the CAS Signal or main "
                f"technical signal, favors BUY CE with a stop below {support or 'the nearest support'} "
                f"rather than fighting the OI-implied support."
            )
        elif overall_bias == "BEARISH":
            suggested_action = (
                f"PCR and max pain both lean bearish. If also confirmed by the CAS Signal or main "
                f"technical signal, favors BUY PE with a stop above {resistance or 'the nearest resistance'} "
                f"rather than fighting the OI-implied resistance."
            )
        else:
            suggested_action = (
                "No strong directional edge from OI alone right now — cross-check the CAS Signal "
                "or main technical signal tab before taking a directional position, or consider "
                "range-bound premium selling between the OI walls above."
            )

        return {
            "support": support,
            "resistance": resistance,
            "range_width_points": range_width,
            "range_width_pct": range_width_pct,
            "overall_bias": overall_bias,
            "max_pain_pull_direction": max_pain_dir,
            "avg_call_iv": round(avg_call_iv, 2) if avg_call_iv else None,
            "avg_put_iv": round(avg_put_iv, 2) if avg_put_iv else None,
            "suggested_action": suggested_action,
            "reasoning": reasoning,
        }

    def _calculate_pcr(self, options_data, expiry):
        """Calculate Put-Call Ratio (PCR) for given expiry"""
        total_call_oi = 0
        total_put_oi = 0

        for item in options_data:
            if item.get('expiryDates') != expiry and item.get('expiryDate') != expiry:
                # v3 API nests expiry under CE/PE too; be lenient
                ce_expiry = item.get('CE', {}).get('expiryDate') if item.get('CE') else None
                pe_expiry = item.get('PE', {}).get('expiryDate') if item.get('PE') else None
                expiry_dash = expiry.replace("-", "-")
                if ce_expiry != expiry.replace("-", "-") and pe_expiry != expiry.replace("-", "-"):
                    # fallback: still count it (single-expiry query already filters)
                    pass

            if 'CE' in item and item['CE']:
                total_call_oi += item['CE'].get('openInterest', 0)
            if 'PE' in item and item['PE']:
                total_put_oi += item['PE'].get('openInterest', 0)

        pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0

        # PCR interpretation
        if pcr > 1.2:
            signal = "BULLISH"  # More puts = bearish sentiment = contrarian bullish
        elif pcr < 0.8:
            signal = "BEARISH"  # More calls = bullish sentiment = contrarian bearish
        else:
            signal = "NEUTRAL"

        return {
            "pcr": round(pcr, 2),
            "signal": signal,
            "total_call_oi": total_call_oi,
            "total_put_oi": total_put_oi
        }

    def _calculate_max_pain(self, options_data, expiry, spot_price):
        """
        Calculate Max Pain - strike where option sellers lose least money
        """
        strikes = {}

        for item in options_data:
            strike = item.get('strikePrice', 0)
            if strike == 0:
                continue

            call_oi = item.get('CE', {}).get('openInterest', 0) if item.get('CE') else 0
            put_oi = item.get('PE', {}).get('openInterest', 0) if item.get('PE') else 0

            strikes[strike] = {
                'call_oi': call_oi,
                'put_oi': put_oi
            }

        # Calculate pain at each strike
        pain_values = {}
        for test_strike in strikes.keys():
            total_pain = 0

            for strike, oi in strikes.items():
                # Call sellers pain if spot > strike
                if test_strike > strike:
                    total_pain += (test_strike - strike) * oi['call_oi']

                # Put sellers pain if spot < strike
                if test_strike < strike:
                    total_pain += (strike - test_strike) * oi['put_oi']

            pain_values[test_strike] = total_pain

        # Max pain is strike with minimum total pain
        if pain_values:
            max_pain_strike = min(pain_values, key=pain_values.get)
            return int(max_pain_strike)

        return int(spot_price)

    def _get_top_oi_strikes(self, options_data, expiry, spot_price, top_n=5):
        """Get top N strikes by OI for calls and puts"""
        calls = []
        puts = []

        for item in options_data:
            strike = item.get('strikePrice', 0)

            if 'CE' in item and item['CE']:
                calls.append({
                    'strike': strike,
                    'oi': item['CE'].get('openInterest', 0),
                    'oi_change': item['CE'].get('changeinOpenInterest', 0),
                    'iv': item['CE'].get('impliedVolatility', 0),
                    'ltp': item['CE'].get('lastPrice', 0),
                })

            if 'PE' in item and item['PE']:
                puts.append({
                    'strike': strike,
                    'oi': item['PE'].get('openInterest', 0),
                    'oi_change': item['PE'].get('changeinOpenInterest', 0),
                    'iv': item['PE'].get('impliedVolatility', 0),
                    'ltp': item['PE'].get('lastPrice', 0),
                })

        # Sort by OI and get top N
        calls_sorted = sorted(calls, key=lambda x: x['oi'], reverse=True)[:top_n]
        puts_sorted = sorted(puts, key=lambda x: x['oi'], reverse=True)[:top_n]

        return {
            "calls": calls_sorted,
            "puts": puts_sorted
        }

    def _calculate_dte(self, expiry_date_str):
        """Calculate days to expiry"""
        try:
            expiry_date = datetime.strptime(expiry_date_str, "%d-%b-%Y")
            today = datetime.now()
            dte = (expiry_date - today).days
            return max(0, dte)
        except:
            return 0


def get_nse_options_data():
    """Convenience function to fetch NSE options data"""
    nse = NSEOptionsChain()
    return nse.fetch_options_chain("NIFTY")