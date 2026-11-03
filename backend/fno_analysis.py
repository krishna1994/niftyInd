"""
F&O (Futures & Options) data analysis to help predict CAS closing-window moves.

Downloads NSE's daily UDiFF bhavcopy (F&O) for each trading day already analyzed
in cas_analysis.py, extracts NIFTY-specific features:
  - Near-month futures OI, change in OI, volume, basis (fut - spot)
  - Options PCR (Put/Call OI ratio) for the nearest weekly expiry
  - Total options OI (calls + puts) for nearest expiry
  - ATM strike distance / OI concentration

Merges these F&O features with the closing-window move data from
cas_analysis_output.csv and re-runs correlation / pattern analysis to see
if F&O positioning helps predict end-of-day (CAS) volatility.
"""
import requests
import zipfile
import io
import pandas as pd
import numpy as np
from datetime import datetime
import time
import os

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
CACHE_DIR = os.path.join(os.path.dirname(__file__), "fno_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def fetch_fno_bhavcopy(date_str):
    """
    date_str: 'YYYY-MM-DD'
    Returns a DataFrame of that day's F&O bhavcopy, or None if unavailable
    (weekends/holidays/no data).
    """
    d = datetime.strptime(date_str, "%Y-%m-%d")
    yyyymmdd = d.strftime("%Y%m%d")

    cache_path = os.path.join(CACHE_DIR, f"{yyyymmdd}.csv")
    if os.path.exists(cache_path):
        try:
            return pd.read_csv(cache_path)
        except Exception:
            pass

    url = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{yyyymmdd}_F_0000.csv.zip"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200 or len(resp.content) < 1000:
            return None
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        name = z.namelist()[0]
        with z.open(name) as f:
            df = pd.read_csv(f)
        df.to_csv(cache_path, index=False)
        return df
    except Exception as e:
        print(f"  [warn] failed to fetch F&O bhavcopy for {date_str}: {e}")
        return None


def extract_nifty_features(df, date_str):
    """Extract NIFTY futures + options features from one day's bhavcopy."""
    if df is None or df.empty:
        return None

    nifty = df[df["TckrSymb"] == "NIFTY"]
    if nifty.empty:
        return None

    # --- Futures (IDF): pick nearest expiry (min XpryDt) ---
    futs = nifty[nifty["FinInstrmTp"] == "IDF"].copy()
    fut_row = None
    if not futs.empty:
        futs["XpryDt"] = pd.to_datetime(futs["XpryDt"])
        futs = futs.sort_values("XpryDt")
        fut_row = futs.iloc[0]

    # --- Options (IDO): pick nearest expiry ---
    opts = nifty[nifty["FinInstrmTp"] == "IDO"].copy()
    pcr = np.nan
    total_call_oi = np.nan
    total_put_oi = np.nan
    call_oi_chg = np.nan
    put_oi_chg = np.nan

    if not opts.empty:
        opts["XpryDt"] = pd.to_datetime(opts["XpryDt"])
        nearest_expiry = opts["XpryDt"].min()
        near_opts = opts[opts["XpryDt"] == nearest_expiry]

        calls = near_opts[near_opts["OptnTp"] == "CE"]
        puts = near_opts[near_opts["OptnTp"] == "PE"]

        total_call_oi = calls["OpnIntrst"].sum()
        total_put_oi = puts["OpnIntrst"].sum()
        call_oi_chg = calls["ChngInOpnIntrst"].sum()
        put_oi_chg = puts["ChngInOpnIntrst"].sum()
        pcr = total_put_oi / total_call_oi if total_call_oi else np.nan

    spot = fut_row["UndrlygPric"] if fut_row is not None else np.nan
    fut_close = fut_row["ClsPric"] if fut_row is not None else np.nan
    fut_oi = fut_row["OpnIntrst"] if fut_row is not None else np.nan
    fut_oi_chg = fut_row["ChngInOpnIntrst"] if fut_row is not None else np.nan
    fut_vol = fut_row["TtlTradgVol"] if fut_row is not None else np.nan
    basis = (fut_close - spot) if (fut_row is not None and pd.notna(spot)) else np.nan

    return {
        "date": date_str,
        "spot": spot,
        "fut_close": fut_close,
        "fut_basis": basis,
        "fut_oi": fut_oi,
        "fut_oi_chg": fut_oi_chg,
        "fut_volume": fut_vol,
        "pcr": pcr,
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
        "call_oi_chg": call_oi_chg,
        "put_oi_chg": put_oi_chg,
    }


def build_fno_dataset(dates):
    rows = []
    for i, d in enumerate(dates):
        print(f"[{i+1}/{len(dates)}] fetching F&O bhavcopy for {d} ...")
        df = fetch_fno_bhavcopy(d)
        feat = extract_nifty_features(df, d)
        if feat:
            rows.append(feat)
        else:
            print(f"  -> no F&O data for {d} (holiday/unavailable)")
        time.sleep(0.3)  # be polite to NSE archives
    return pd.DataFrame(rows)


if __name__ == "__main__":
    cas_path = os.path.join(os.path.dirname(__file__), "cas_analysis_output.csv")
    cas_df = pd.read_csv(cas_path)
    dates = cas_df["date"].tolist()

    fno_df = build_fno_dataset(dates)
    fno_out = os.path.join(os.path.dirname(__file__), "fno_features_output.csv")
    fno_df.to_csv(fno_out, index=False)
    print(f"\nSaved F&O features for {len(fno_df)}/{len(dates)} days to {fno_out}")

    # Merge with closing-window move data
    merged = cas_df.merge(fno_df, on="date", how="inner")
    merged["fut_oi_chg_pct"] = merged["fut_oi_chg"] / (merged["fut_oi"] - merged["fut_oi_chg"] + 1e-9) * 100

    merged_out = os.path.join(os.path.dirname(__file__), "cas_fno_merged.csv")
    merged.to_csv(merged_out, index=False)
    print(f"Saved merged dataset ({len(merged)} rows) to {merged_out}\n")

    print("=== Correlations with closing-window move (close_move_pct) ===")
    features = ["pcr", "fut_basis", "fut_oi_chg", "fut_oi_chg_pct", "fut_volume",
                "call_oi_chg", "put_oi_chg"]
    for feat in features:
        if feat in merged.columns:
            corr = merged[feat].corr(merged["close_move_pct"])
            corr_abs = merged[feat].corr(merged["abs_close_move_pct"])
            print(f"{feat:20s}  corr(vs signed move)={corr:+.3f}   corr(vs |move|)={corr_abs:+.3f}")

    print("\n=== PCR level vs next closing-window reversal rate ===")
    merged["pcr_bucket"] = pd.cut(merged["pcr"], bins=[0, 0.8, 1.0, 1.2, 5],
                                   labels=["<0.8 (bearish OI)", "0.8-1.0", "1.0-1.2", ">1.2 (bullish OI)"])
    print(merged.groupby("pcr_bucket")["abs_close_move_pct"].agg(["mean", "count"]))

    print("\n=== High futures OI build-up days vs closing move magnitude ===")
    merged["oi_chg_bucket"] = pd.qcut(merged["fut_oi_chg_pct"].rank(method="first"), 3,
                                       labels=["Low OI chg", "Mid OI chg", "High OI chg"])
    print(merged.groupby("oi_chg_bucket")["abs_close_move_pct"].agg(["mean", "count"]))