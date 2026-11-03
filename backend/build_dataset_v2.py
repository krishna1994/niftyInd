"""
Expanded dataset build: adds cross-asset / macro features to the existing
master_dataset.csv, since 60-minute intraday history is capped at ~2 years
by Yahoo Finance (matching our current 492-day dataset). The practical way
to "get more data" for this model, given that hard cap, is to enrich each
existing day with MORE PREDICTIVE FEATURES from correlated markets:

  - Bank Nifty daily move (India's most-traded index, high correlation with Nifty)
  - USD/INR daily move (FII flow proxy — currency weakness often precedes
    Nifty weakness)
  - Crude oil (Brent/WTI) daily move (India is a major oil importer;
    oil spikes are a classic Nifty headwind)
  - US Dow Jones overnight move (global risk-on/risk-off cue, feeds into
    next-day Indian market open/sentiment)
  - Global VIX (US) level (global risk appetite, complements India VIX)

All cross-asset features are LAGGED by 1 day (yesterday's close) to avoid
lookahead — consistent with the rest of the pipeline.

Output: backend/master_dataset_v2.csv (all v1 columns + new cross-asset cols)
"""
import os
import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(__file__)
V1_PATH = os.path.join(HERE, "master_dataset.csv")
V2_PATH = os.path.join(HERE, "master_dataset_v2.csv")

CROSS_ASSET_TICKERS = {
    "^NSEBANK": "banknifty",
    "USDINR=X": "usdinr",
    "CL=F": "crude",
    "^DJI": "dow",
    "^VIX": "global_vix",
}


def fetch_cross_asset_data(period="2y"):
    """Fetch daily close prices for all cross-asset tickers."""
    frames = {}
    for ticker, name in CROSS_ASSET_TICKERS.items():
        print(f"Fetching {name} ({ticker})...")
        df = yf.download(ticker, period=period, interval="1d", progress=False)
        if hasattr(df.columns, "get_level_values"):
            df.columns = df.columns.get_level_values(0)
        df.columns = [str(c).strip() for c in df.columns]
        if df.empty or "Close" not in df.columns:
            print(f"  WARNING: no data for {name}")
            continue
        s = df["Close"].copy()
        s.index = pd.to_datetime(s.index).date
        frames[name] = s
    return frames


def build_cross_asset_features(cross_data, dates):
    """
    For each date in `dates`, compute the daily % change (close-to-close)
    of each cross-asset series as of the PREVIOUS trading day relative to
    that date (i.e., lag1 — the info available before today's session).
    """
    rows = []
    for name, series in cross_data.items():
        series = series.sort_index()
        pct_change = series.pct_change() * 100
        rows.append(pct_change.rename(f"{name}_chg_pct"))
        rows.append(series.rename(f"{name}_close"))

    combined = pd.concat(rows, axis=1)
    combined.index = pd.to_datetime(combined.index)
    return combined


def main():
    print("Loading existing master_dataset.csv (v1)...")
    v1 = pd.read_csv(V1_PATH, parse_dates=["date"])
    v1 = v1.sort_values("date").reset_index(drop=True)
    print(f"  {len(v1)} rows loaded")

    cross_data = fetch_cross_asset_data(period="2y")
    combined = build_cross_asset_features(cross_data, v1["date"])

    # Merge: for each day D in v1, attach the PREVIOUS trading day's
    # cross-asset values (lag1, no lookahead) by shifting the combined
    # cross-asset frame by 1 row (since it's already daily-indexed and
    # sorted, shift(1) gives "yesterday's" value aligned to today's date).
    combined_lag1 = combined.shift(1)
    combined_lag1.columns = [f"{c}_lag1" for c in combined_lag1.columns]

    v1_indexed = v1.set_index("date")
    merged = v1_indexed.join(combined_lag1, how="left")
    merged = merged.reset_index()

    # Fill small gaps (holidays mismatch between markets) via forward-fill
    cross_cols = [c for c in merged.columns if c.endswith("_lag1")]
    merged[cross_cols] = merged[cross_cols].ffill()

    merged.to_csv(V2_PATH, index=False)
    print(f"\nSaved expanded dataset: {len(merged)} rows, {len(merged.columns)} columns -> {V2_PATH}")
    print(f"New cross-asset columns added: {cross_cols}")
    print("\nMissing value check (should be near-zero after ffill, except very first few rows):")
    print(merged[cross_cols].isna().sum())


if __name__ == "__main__":
    main()