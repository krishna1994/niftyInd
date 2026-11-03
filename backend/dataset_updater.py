"""
Incremental daily dataset updater for the CAS signal models.

PROBLEM THIS SOLVES:
  build_dataset.py / build_dataset_v2.py were originally one-off scripts you
  run manually — master_dataset.csv and master_dataset_v2.csv were static
  snapshots that never grew after being created. cas_service.py retrains
  the RandomForest models periodically, but it was always retraining on the
  SAME frozen historical data — it was NOT learning from new trading days
  as they happened. Live requests only used fresh data for INFERENCE
  (spot/VIX/option-chain), never for actually growing the training set.

WHAT THIS MODULE DOES:
  Once per day (checked via a background thread started at server startup —
  see main.py), this:
    1. Fetches the latest available trading day(s) not yet present in
       master_dataset.csv (via the same yfinance + NSE bhavcopy sources
       used by build_dataset.py).
    2. Appends only the NEW rows (idempotent — safe to run multiple times
       a day, it just no-ops if nothing new is available yet).
    3. Re-derives master_dataset_v2.csv (adds the cross-asset columns) from
       the updated v1 dataset.
    4. Re-fits the isotonic probability calibrators on the updated data.
  Writing to these CSV files updates their mtime, which cas_service.py's
  existing `_needs_retrain()` check already watches for — so the next
  request after an update automatically retrains the live models on the
  larger, more current dataset. No changes needed to cas_service.py.

WHY DAILY, NOT MORE FREQUENT:
  The model's target label (`close_move_pct`, `abs_close_move_pct`) is only
  knowable once a trading day has FULLY closed — trying to add "today" to
  the training set while the market is still open would leak an incomplete/
  wrong outcome into the data. So this only ever adds fully-completed past
  trading days, and checking once daily (after market close) is sufficient.
"""
import os
import time
import logging
import threading
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from build_dataset import (
    fetch_price_and_vix,
    build_price_features,
    fetch_fno_bhavcopy,
    extract_nifty_features,
)

logger = logging.getLogger(__name__)

HERE = os.path.dirname(__file__)
V1_PATH = os.path.join(HERE, "master_dataset.csv")
V2_PATH = os.path.join(HERE, "master_dataset_v2.csv")

# How often the background thread wakes up to CHECK whether an update is due.
# The actual update itself only proceeds if there's genuinely a new
# completed trading day not yet in the dataset (see _has_new_data_available).
CHECK_INTERVAL_SECONDS = 6 * 60 * 60  # check every 6 hours


def _load_existing_dates() -> set:
    if not os.path.exists(V1_PATH):
        return set()
    df = pd.read_csv(V1_PATH, usecols=["date"])
    return set(pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"))


def _fetch_new_price_rows(existing_dates: set) -> pd.DataFrame:
    """Re-fetch the last ~2y of intraday price data (yfinance's own history
    cap) and return only the rows for dates not already in our dataset."""
    price_df, vix = fetch_price_and_vix()
    price_features = build_price_features(price_df)
    price_features["date"] = price_features["date"].astype(str)
    new_rows = price_features[~price_features["date"].isin(existing_dates)].copy()
    if new_rows.empty:
        return new_rows, vix
    return new_rows, vix


def _fetch_fno_for_dates(dates: list) -> pd.DataFrame:
    rows = []
    for d in dates:
        df = fetch_fno_bhavcopy(d)
        feat = extract_nifty_features(df, d)
        if feat:
            rows.append(feat)
        time.sleep(0.15)
    return pd.DataFrame(rows)


def update_v1_dataset() -> int:
    """
    Append any newly-completed trading day(s) to master_dataset.csv.
    Returns the number of new rows appended (0 if nothing new).
    """
    existing_dates = _load_existing_dates()
    new_price_rows, vix = _fetch_new_price_rows(existing_dates)

    if new_price_rows.empty:
        logger.info("dataset_updater: no new trading days available yet")
        return 0

    new_dates = new_price_rows["date"].tolist()
    logger.info(f"dataset_updater: found {len(new_dates)} new day(s): {new_dates}")

    fno_new = _fetch_fno_for_dates(new_dates)
    if fno_new.empty:
        logger.warning(
            "dataset_updater: F&O bhavcopy not yet available for new date(s) "
            "(NSE archive usually lags by ~1 day) — skipping this cycle"
        )
        return 0

    fno_new["date"] = fno_new["date"].astype(str)
    merged_new = new_price_rows.merge(fno_new, on="date", how="inner")
    if merged_new.empty:
        logger.info("dataset_updater: new price rows had no matching F&O data yet")
        return 0

    merged_new["vix"] = merged_new["date"].map(
        lambda d: vix.get(pd.Timestamp(d).date(), np.nan)
    )
    merged_new["fut_oi_chg_pct"] = (
        merged_new["fut_oi_chg"] / (merged_new["fut_oi"] - merged_new["fut_oi_chg"] + 1e-9) * 100
    )

    existing = pd.read_csv(V1_PATH)
    # Align columns defensively in case of any ordering differences
    merged_new = merged_new[existing.columns]
    combined = pd.concat([existing, merged_new], ignore_index=True)
    combined = combined.drop_duplicates(subset=["date"], keep="last")
    combined = combined.sort_values("date").reset_index(drop=True)

    combined.to_csv(V1_PATH, index=False)
    n_added = len(combined) - len(existing)
    logger.info(f"dataset_updater: master_dataset.csv grew by {n_added} row(s) -> {len(combined)} total")
    return n_added


def rebuild_v2_dataset():
    """Re-derive master_dataset_v2.csv (cross-asset features) from the
    freshly-updated v1 dataset."""
    import build_dataset_v2
    build_dataset_v2.main()


def refresh_calibrators():
    """Re-fit isotonic probability calibrators on the updated data."""
    import cas_calibration
    cas_calibration.fit_calibrators()


def run_daily_update_cycle():
    """
    Full pipeline: append new day(s) -> rebuild v2 -> refresh calibrators.
    Safe to call repeatedly; each step no-ops gracefully if there's nothing
    new to do. Any failure is logged and swallowed so it never crashes the
    live server — worst case, the models just keep using the last-known-good
    dataset until the next successful cycle.
    """
    try:
        n_added = update_v1_dataset()
        if n_added > 0:
            logger.info("dataset_updater: rebuilding master_dataset_v2.csv with new data...")
            rebuild_v2_dataset()
            logger.info("dataset_updater: refreshing probability calibrators with new data...")
            refresh_calibrators()
            logger.info(
                f"dataset_updater: daily update complete — {n_added} new trading "
                f"day(s) incorporated. Live models will retrain on next request "
                f"(cas_service.py detects the updated file automatically)."
            )
    except Exception as e:
        logger.error(f"dataset_updater: daily update cycle failed (will retry next cycle): {e}")


def start_background_updater():
    """
    Launch a daemon thread that periodically checks for and incorporates new
    trading days. Call this once at server startup (see main.py).
    """
    def _loop():
        # Run once shortly after startup (give the server a moment to finish
        # booting first), then repeat on CHECK_INTERVAL_SECONDS.
        time.sleep(30)
        while True:
            run_daily_update_cycle()
            time.sleep(CHECK_INTERVAL_SECONDS)

    thread = threading.Thread(target=_loop, daemon=True)
    thread.start()
    logger.info(
        f"dataset_updater: background updater started "
        f"(checks every {CHECK_INTERVAL_SECONDS // 3600}h for new completed trading days)"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_daily_update_cycle()