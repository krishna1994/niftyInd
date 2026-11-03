"""
CAS Signal Service — a fast, cached wrapper around cas_live_signal.py's
model training + live inference, designed for use behind a FastAPI endpoint
that may be polled frequently by a frontend UI.

Why this exists:
  generate_live_signal() in cas_live_signal.py retrains two RandomForest
  models from scratch (on ~480 historical days) EVERY time it's called —
  taking several seconds. That's fine for a one-off CLI run, but far too
  slow for a UI that needs to feel fast/responsive.

This module:
  1. Trains the models ONCE and caches them in memory (module-level singleton).
  2. Automatically retrains once per calendar day (or when master_dataset*.csv
     files change on disk), since the training data itself only updates
     once a day (F&O bhavcopy is EOD data).
  3. On each request, only re-fetches the FAST parts (live spot, live VIX,
     live cross-asset closes, live NSE option chain) and reuses the cached
     trained models for inference — this makes each request take a fraction
     of a second instead of several seconds.
  4. Wraps everything in try/except so a single failed external API call
     (NSE, yfinance) degrades gracefully instead of crashing the whole
     response — important for a UI that needs to stay usable even if one
     data source is temporarily down.
"""
import os
import math
import time
import threading
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from cas_live_signal import (
    train_final_models,
    get_live_intraday_snapshot,
    get_live_vix,
    get_lagged_fno_features,
    get_lagged_fno_features_2days_ago,
    get_recent_history_features,
    get_live_cross_asset_features,
    directional_bias_ml,
    check_high_conviction_rule,
    suggest_strike,
    _build_X,
    get_cas_implied_spot,
    _is_cas_window,
)
from cas_calibration import load_calibrators
from nse_options import NSEOptionsChain

logger = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)
DATASET_PATH = os.path.join(HERE, "master_dataset.csv")
DATASET_V2_PATH = os.path.join(HERE, "master_dataset_v2.csv")

# ── Module-level cache ───────────────────────────────────────────────────────
_cache_lock = threading.Lock()
_cache = {
    "trained_at": None,          # datetime when models were last trained
    "dataset_mtime": None,       # mtime of dataset files at train time
    "big_move_model": None,
    "dir_model": None,
    "df_v1": None,
    "feature_cols_v1": None,
    "df_v2": None,
    "feature_cols_v2": None,
    "iso_dir": None,
    "iso_big": None,
}

RETRAIN_MAX_AGE_SECONDS = 6 * 60 * 60  # retrain at most every 6 hours


def _dataset_mtime():
    """Return the latest mtime across both dataset CSVs (0 if missing)."""
    mtimes = []
    for p in (DATASET_PATH, DATASET_V2_PATH):
        if os.path.exists(p):
            mtimes.append(os.path.getmtime(p))
    return max(mtimes) if mtimes else 0


def _needs_retrain():
    if _cache["trained_at"] is None:
        return True
    age = (datetime.now() - _cache["trained_at"]).total_seconds()
    if age > RETRAIN_MAX_AGE_SECONDS:
        return True
    if _cache["dataset_mtime"] != _dataset_mtime():
        return True
    return False


def ensure_models_trained():
    """Train (or reuse cached) models. Thread-safe. Fast on cache hit."""
    if not _needs_retrain():
        return

    with _cache_lock:
        if not _needs_retrain():  # re-check inside lock (another thread may have trained)
            return
        logger.info("Training CAS models (cache miss / stale)...")
        t0 = time.time()
        big_move_model, dir_model, df_v1, feature_cols_v1, df_v2, feature_cols_v2 = train_final_models()
        iso_dir, iso_big = load_calibrators()

        _cache.update({
            "trained_at": datetime.now(),
            "dataset_mtime": _dataset_mtime(),
            "big_move_model": big_move_model,
            "dir_model": dir_model,
            "df_v1": df_v1,
            "feature_cols_v1": feature_cols_v1,
            "df_v2": df_v2,
            "feature_cols_v2": feature_cols_v2,
            "iso_dir": iso_dir,
            "iso_big": iso_big,
        })
        logger.info(f"CAS models trained in {time.time() - t0:.2f}s")


def warm_start():
    """Call this once at FastAPI startup so the first user request is fast."""
    try:
        ensure_models_trained()
    except Exception as e:
        logger.error(f"CAS warm_start failed (will retry lazily on first request): {e}")


def _build_live_feature_row_parallel():
    """
    Parallelized version of cas_live_signal.build_live_feature_row().
    The original fetches intraday snapshot, VIX, F&O bhavcopy (x2), recent
    history, and 5 cross-asset tickers ALL sequentially — each yfinance/NSE
    call has network latency, so doing them one-by-one is the main reason
    a single request took ~7 seconds. Running them concurrently via a
    thread pool cuts this down to roughly the slowest single call's time.
    """
    with ThreadPoolExecutor(max_workers=8) as executor:
        f_intraday = executor.submit(get_live_intraday_snapshot)
        f_vix = executor.submit(get_live_vix)
        f_fno = executor.submit(get_lagged_fno_features)
        f_recent = executor.submit(get_recent_history_features)
        f_cross = executor.submit(get_live_cross_asset_features)

        intraday = f_intraday.result()
        vix = f_vix.result()
        fno_feat, fno_date = f_fno.result()
        recent = f_recent.result()
        cross_asset = f_cross.result()

        # ── CAS window: update intraday snapshot with implied spot ────────────
        # get_live_intraday_snapshot() was called without option chain data
        # (it runs concurrently with the chain fetch). Now that we have the
        # chain, if we're in the CAS window, recompute the spot price using
        # put-call parity so the feature row reflects the live CAS equilibrium
        # price rather than the frozen 3:30 PM yfinance price.
        # We do this INSIDE the executor context so the chain fetch (f_oc in
        # the outer scope) hasn't been awaited yet — we use a separate
        # inner chain fetch here to avoid a circular dependency.
        if _is_cas_window():
            try:
                from nse_options import NSEOptionsChain as _NSEChain
                _oc = _NSEChain().fetch_options_chain("NIFTY")
                if _oc:
                    _cas = get_cas_implied_spot(_oc)
                    if _cas.get("implied_spot") and _cas.get("method") == "put_call_parity":
                        _new_spot = _cas["implied_spot"]
                        _day_open = intraday["day_open"]
                        intraday = dict(intraday)
                        intraday["spot"] = _new_spot
                        intraday["main_move_pct"] = (_new_spot - _day_open) / _day_open * 100
                        intraday["abs_main_move"] = abs(intraday["main_move_pct"])
                        intraday["cas_info"] = _cas
                        logger.info(
                            f"CAS window: replaced frozen yfinance spot {intraday.get('spot', '?')} "
                            f"with put-call-parity implied spot {_new_spot} "
                            f"(ATM {_cas.get('atm_strike')}: C={_cas.get('atm_call_ltp')} P={_cas.get('atm_put_ltp')})"
                        )
            except Exception as _e:
                logger.warning(f"CAS implied spot update failed (non-fatal): {_e}")

        fno_feat_prev, fno_date_prev = (None, None)
        if fno_date:
            fno_feat_prev, fno_date_prev = get_lagged_fno_features_2days_ago(fno_date)

    dow = datetime.now().strftime("%A")
    dow_flags = {f"dow_{d}": 0 for d in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]}
    if f"dow_{dow}" in dow_flags:
        dow_flags[f"dow_{dow}"] = 1

    basis_change = np.nan
    pcr_change = np.nan
    if fno_feat and fno_feat_prev:
        if pd.notna(fno_feat.get("fut_basis")) and pd.notna(fno_feat_prev.get("fut_basis")):
            basis_change = fno_feat["fut_basis"] - fno_feat_prev["fut_basis"]
        if pd.notna(fno_feat.get("pcr")) and pd.notna(fno_feat_prev.get("pcr")):
            pcr_change = fno_feat["pcr"] - fno_feat_prev["pcr"]

    row = {
        "fut_basis_lag1": fno_feat["fut_basis"] if fno_feat else np.nan,
        "fut_oi_chg_pct_lag1": fno_feat["fut_oi_chg"] / (fno_feat["fut_oi"] - fno_feat["fut_oi_chg"] + 1e-9) * 100 if fno_feat else np.nan,
        "fut_volume_lag1": fno_feat["fut_volume"] if fno_feat else np.nan,
        "pcr_lag1": fno_feat["pcr"] if fno_feat else np.nan,
        "call_oi_chg_lag1": fno_feat["call_oi_chg"] if fno_feat else np.nan,
        "put_oi_chg_lag1": fno_feat["put_oi_chg"] if fno_feat else np.nan,
        "vix_lag1": vix,
        "days_to_expiry_lag1": fno_feat["days_to_expiry"] if fno_feat else np.nan,
        "day_range_pct_lag1": intraday["day_range_pct"],
        "abs_main_move": intraday["abs_main_move"],
        "main_move_pct": intraday["main_move_pct"],
        "rolling5_abs_close_move": recent["rolling5_abs_close_move"],
        "rolling10_abs_close_move": recent["rolling10_abs_close_move"],
        "prev_close_move": recent["prev_close_move"],
        "prev_close_move2": recent["prev_close_move2"],
        "basis_change": basis_change,
        "pcr_change": pcr_change,
        "is_expiry_day": int(fno_feat["days_to_expiry"] <= 1) if fno_feat and pd.notna(fno_feat.get("days_to_expiry")) else 0,
    }
    row.update(dow_flags)
    row.update(cross_asset)

    meta = {
        "intraday": intraday,
        "vix": vix,
        "fno_feat": fno_feat,
        "fno_date": fno_date,
        "cross_asset": cross_asset,
    }
    return row, meta


# ── Short-TTL result cache ───────────────────────────────────────────────────
# During market hours a user may have the UI open and auto-refreshing every
# few seconds. Without this cache, EVERY refresh would re-hit yfinance/NSE
# (7 external calls) even if nothing has meaningfully changed. A short TTL
# (default 15s) makes rapid UI polling feel instant while still keeping data
# reasonably fresh relative to how fast Nifty actually moves.
_result_cache_lock = threading.Lock()
_result_cache = {"data": None, "fetched_at": 0.0}
RESULT_CACHE_TTL_SECONDS = 15


def get_live_cas_signal(force_refresh: bool = False):
    """
    Fast path: reuse cached trained models, only fetch live data (in
    parallel) + run inference. Returns the same shape as
    cas_live_signal.generate_live_signal() but without print statements,
    with graceful degradation on partial failures, and with a short-TTL
    result cache to keep rapid UI polling fast.
    """
    now = time.time()
    if not force_refresh:
        with _result_cache_lock:
            if _result_cache["data"] is not None and (now - _result_cache["fetched_at"]) < RESULT_CACHE_TTL_SECONDS:
                cached = dict(_result_cache["data"])
                cached["cache_hit"] = True
                cached["cache_age_seconds"] = round(now - _result_cache["fetched_at"], 1)
                return cached

    ensure_models_trained()

    big_move_model = _cache["big_move_model"]
    dir_model = _cache["dir_model"]
    df_v1 = _cache["df_v1"]
    feature_cols_v1 = _cache["feature_cols_v1"]
    df_v2 = _cache["df_v2"]
    feature_cols_v2 = _cache["feature_cols_v2"]
    iso_dir = _cache["iso_dir"]
    iso_big = _cache["iso_big"]

    warnings = []

    def _fetch_option_chain():
        try:
            nse = NSEOptionsChain()
            return nse.fetch_options_chain("NIFTY")
        except Exception as e:
            logger.error(f"NSE option chain fetch failed: {e}")
            return None

    # Fetch the option chain concurrently with the feature-row build (both
    # are network-bound and independent of each other).
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_row = executor.submit(_build_live_feature_row_parallel)
        f_oc = executor.submit(_fetch_option_chain)

        try:
            row, meta = f_row.result()
        except Exception as e:
            logger.error(f"Failed to build live feature row: {e}")
            raise RuntimeError(f"Could not fetch live market data: {e}")

        oc_data = f_oc.result()
        if oc_data is None:
            warnings.append("Live option chain data unavailable (NSE may be rate-limiting or closed)")

    try:
        X_big_live = _build_X(row, feature_cols_v1, df_v1, feature_cols_v1)
        big_move_prob = float(big_move_model.predict_proba(X_big_live)[0, 1])
    except Exception as e:
        logger.error(f"Big-move inference failed: {e}")
        big_move_prob = None
        warnings.append("Big-move risk could not be computed")

    if big_move_prob is not None:
        if big_move_prob >= 0.55:
            risk_level = "HIGH"
        elif big_move_prob >= 0.35:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"
    else:
        risk_level = "UNKNOWN"

    try:
        X_dir_live = _build_X(row, feature_cols_v2, df_v2, feature_cols_v2)
        bias, prob_up, reasoning = directional_bias_ml(dir_model, X_dir_live, row)
    except Exception as e:
        logger.error(f"Directional inference failed: {e}")
        bias, prob_up, reasoning = "UNKNOWN", None, ["Directional model unavailable"]
        warnings.append("Directional bias could not be computed")

    # ── CAS window: add implied spot info to reasoning ───────────────────────
    intraday_meta = meta.get("intraday", {})
    cas_info = intraday_meta.get("cas_info")
    if cas_info and cas_info.get("method") == "put_call_parity":
        reasoning.insert(0,
            f"🔔 CAS window active: spot price computed via put-call parity "
            f"(ATM {cas_info.get('atm_strike')}: C=₹{cas_info.get('atm_call_ltp')} "
            f"P=₹{cas_info.get('atm_put_ltp')}) → implied spot ₹{cas_info.get('implied_spot')} "
            f"(regular market frozen at 3:30 PM)"
        )

    if meta.get("cross_asset"):
        ca = meta["cross_asset"]
        if pd.notna(ca.get("banknifty_chg_pct_lag1")):
            reasoning.append(f"Bank Nifty last close chg: {ca['banknifty_chg_pct_lag1']:+.2f}%")
        if pd.notna(ca.get("usdinr_chg_pct_lag1")):
            reasoning.append(f"USD/INR last close chg: {ca['usdinr_chg_pct_lag1']:+.2f}%")
        if pd.notna(ca.get("dow_chg_pct_lag1")):
            reasoning.append(f"Dow Jones overnight chg: {ca['dow_chg_pct_lag1']:+.2f}%")

    directional_pop = None
    big_move_pop = None
    try:
        if prob_up is not None and iso_dir is not None:
            directional_pop = float(iso_dir.predict([prob_up])[0])
            if bias == "BEARISH":
                directional_pop = 1 - directional_pop
        if big_move_prob is not None and iso_big is not None:
            big_move_pop = float(iso_big.predict([big_move_prob])[0])
    except Exception as e:
        logger.error(f"POP calibration failed: {e}")
        warnings.append("Probability calibration unavailable")

    try:
        is_high_conviction, hc_detail = check_high_conviction_rule(row)
    except Exception as e:
        logger.error(f"High-conviction rule check failed: {e}")
        is_high_conviction, hc_detail = False, {}

    spot = None
    if oc_data:
        spot = oc_data.get("spot_price")
    if spot is None:
        spot = meta.get("intraday", {}).get("spot")

    strike, action = (None, "UNKNOWN")
    if bias in ("BULLISH", "BEARISH") and spot:
        try:
            strike, action = suggest_strike(oc_data, bias, spot)
        except Exception as e:
            logger.error(f"Strike suggestion failed: {e}")

    result = {
        "success": True,
        "warnings": warnings,
        "high_conviction_signal": is_high_conviction,
        "high_conviction_detail": hc_detail if is_high_conviction else None,
        "timestamp": datetime.now().isoformat(),
        "spot_price": spot,
        "big_move_probability": round(big_move_prob, 3) if big_move_prob is not None else None,
        "big_move_pop": round(big_move_pop, 3) if big_move_pop is not None else None,
        "risk_level": risk_level,
        "directional_bias": bias,
        "directional_confidence": (
            round(float(prob_up if bias == "BULLISH" else 1 - prob_up), 3)
            if prob_up is not None else None
        ),
        "directional_pop": round(directional_pop, 3) if directional_pop is not None else None,
        "suggested_action": action,
        "suggested_strike": strike,
        "reasoning": reasoning,
        "pcr": oc_data["pcr"] if oc_data else None,
        "max_pain": oc_data["max_pain"] if oc_data else None,
        "nearest_expiry": oc_data["nearest_expiry"] if oc_data else None,
        "days_to_expiry": oc_data["days_to_expiry"] if oc_data else None,
        "vix": meta.get("vix"),
        "fno_snapshot_date": meta.get("fno_date"),
        "intraday_main_move_pct": meta.get("intraday", {}).get("main_move_pct"),
        "cas_window_active": bool(cas_info and cas_info.get("method") == "put_call_parity"),
        "cas_implied_spot": cas_info.get("implied_spot") if cas_info else None,
        "top_call_oi": oc_data["top_call_oi"] if oc_data else [],
        "top_put_oi": oc_data["top_put_oi"] if oc_data else [],
        "model_trained_at": _cache["trained_at"].isoformat() if _cache["trained_at"] else None,
        "model_honesty_note": (
            "Backtested walk-forward (out-of-sample, no lookahead) performance on "
            "492 historical trading days: Big-move classifier (v1 features): 67.5% "
            "accuracy, 37.6% precision, 67.6% recall (baseline 22.5%). Directional "
            "classifier (v2 features incl. Bank Nifty/USD-INR/Crude/Dow/Global-VIX "
            "cross-asset data): 62.0% accuracy, 64.9% precision (baseline 52.0%). "
            "This is a genuine statistical edge, NOT a high-confidence guarantee. "
            "A cost-adjusted P&L check showed the average closing-window move "
            "(~0.078%) is thin relative to typical options transaction costs — "
            "use this as a risk/bias tool, not a standalone profit engine. Always "
            "use proper position sizing and stop-loss discipline."
        ),
        "pop_explanation": (
            "POP (Probability Of being correct) is calibrated against actual "
            "historical hit-rates via isotonic regression on walk-forward "
            "out-of-sample predictions — not just the raw model confidence score. "
            "Values are capped to a 5%-90% range due to limited sample size at "
            "extreme confidence levels."
        ),
        "cache_hit": False,
        "cache_age_seconds": 0,
    }

    result = _sanitize_for_json(result)

    with _result_cache_lock:
        _result_cache["data"] = result
        _result_cache["fetched_at"] = time.time()

    return result


def _sanitize_for_json(obj):
    """
    Recursively replace NaN/Inf float values with None throughout a nested
    dict/list structure. Standard JSON does not support NaN/Infinity, and
    FastAPI's default JSONResponse will raise
    "ValueError: Out of range float values are not JSON compliant" if any
    slip through (this happened in practice — e.g. a transient yfinance
    hiccup on one cross-asset ticker leaving a NaN in a numeric field that
    wasn't explicitly None-checked). Sanitizing right before we return/cache
    guarantees the API never 500s on this class of error, regardless of
    which upstream field happened to be NaN.
    """
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    warm_start()
    import json
    print(json.dumps(get_live_cas_signal(), indent=2, default=str))