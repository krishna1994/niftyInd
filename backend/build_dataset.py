"""
Build the master dataset for CAS (closing-auction) signal research.

Combines:
  1. Nifty 60-minute intraday OHLC (yfinance, ~2y history -> 494 trading days)
     -> used to build a "closing window" proxy: last 60m bar (15:15-15:30ish)
        vs previous bar (14:15-15:15), plus daily range/trend features.
  2. Daily India VIX close (yfinance, same 2y history)
  3. NSE F&O daily bhavcopy (UDiFF format, historical archive) for NIFTY:
     - near-month futures OI / OI change / volume / basis
     - nearest-expiry options PCR, call/put OI, call/put OI change
  4. Calendar features: day-of-week, days-to-weekly-expiry

Output: backend/master_dataset.csv  (one row per trading day)
"""
import os
import time
import json
import zipfile
import io
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

HERE = os.path.dirname(__file__)
CACHE_DIR = os.path.join(HERE, "fno_cache")
os.makedirs(CACHE_DIR, exist_ok=True)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ── 1. Price data ──────────────────────────────────────────────────────────

def fetch_price_and_vix():
    print("Fetching 60m Nifty intraday (2y) ...")
    df = yf.download("^NSEI", period="2y", interval="60m", progress=False)
    if hasattr(df.columns, "get_level_values"):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).strip() for c in df.columns]
    df = df[["Open", "High", "Low", "Close"]].copy()
    df.index = df.index.tz_convert("Asia/Kolkata")
    df["date"] = df.index.date
    df["time"] = df.index.time

    print("Fetching daily India VIX (2y) ...")
    vix = yf.download("^INDIAVIX", period="2y", interval="1d", progress=False)
    if hasattr(vix.columns, "get_level_values"):
        vix.columns = vix.columns.get_level_values(0)
    vix.columns = [str(c).strip() for c in vix.columns]
    vix_close = vix["Close"]
    vix_close.index = pd.to_datetime(vix_close.index).date
    return df, vix_close


def build_price_features(df):
    rows = []
    for day, g in df.groupby("date"):
        g = g.sort_index()
        if len(g) < 3:
            continue
        day_open = g["Open"].iloc[0]
        day_high = g["High"].max()
        day_low = g["Low"].min()
        day_range = day_high - day_low
        if day_range == 0:
            continue

        # Closing window proxy = last bar of the day (approx last 60-75 min incl. CAS)
        last_bar = g.iloc[-1]
        prev_bar = g.iloc[-2] if len(g) >= 2 else g.iloc[-1]
        pre_close_price = prev_bar["Close"]
        final_close = last_bar["Close"]

        main_session = g.iloc[:-1]
        main_start_close = main_session["Close"].iloc[0] if len(main_session) else day_open
        main_move_pct = (pre_close_price - main_start_close) / main_start_close * 100

        close_move_pct = (final_close - pre_close_price) / pre_close_price * 100
        close_window_range = last_bar["High"] - last_bar["Low"]
        close_range_pct_of_day = (close_window_range / day_range) * 100

        dow = pd.Timestamp(day).day_name()

        rows.append({
            "date": day,
            "day_of_week": dow,
            "day_open": day_open,
            "day_high": day_high,
            "day_low": day_low,
            "day_range_pct": day_range / day_open * 100,
            "main_move_pct": main_move_pct,
            "close_move_pct": close_move_pct,
            "abs_close_move_pct": abs(close_move_pct),
            "close_range_pct_of_day": close_range_pct_of_day,
            "day_final_close": final_close,
        })
    return pd.DataFrame(rows)


# ── 2. F&O bhavcopy ─────────────────────────────────────────────────────────

def fetch_fno_bhavcopy(date_str):
    d = datetime.strptime(str(date_str), "%Y-%m-%d")
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
            fdf = pd.read_csv(f)
        fdf.to_csv(cache_path, index=False)
        return fdf
    except Exception as e:
        print(f"  [warn] {date_str}: {e}")
        return None


def extract_nifty_features(df, date_str):
    if df is None or df.empty:
        return None
    nifty = df[df["TckrSymb"] == "NIFTY"]
    if nifty.empty:
        return None

    futs = nifty[nifty["FinInstrmTp"] == "IDF"].copy()
    fut_row = None
    if not futs.empty:
        futs["XpryDt"] = pd.to_datetime(futs["XpryDt"])
        futs = futs.sort_values("XpryDt")
        fut_row = futs.iloc[0]

    opts = nifty[nifty["FinInstrmTp"] == "IDO"].copy()
    pcr = call_oi = put_oi = call_oi_chg = put_oi_chg = np.nan
    dte = np.nan
    if not opts.empty:
        opts["XpryDt"] = pd.to_datetime(opts["XpryDt"])
        nearest_expiry = opts["XpryDt"].min()
        near_opts = opts[opts["XpryDt"] == nearest_expiry]
        calls = near_opts[near_opts["OptnTp"] == "CE"]
        puts = near_opts[near_opts["OptnTp"] == "PE"]
        call_oi = calls["OpnIntrst"].sum()
        put_oi = puts["OpnIntrst"].sum()
        call_oi_chg = calls["ChngInOpnIntrst"].sum()
        put_oi_chg = puts["ChngInOpnIntrst"].sum()
        pcr = put_oi / call_oi if call_oi else np.nan
        trade_dt = pd.to_datetime(date_str)
        dte = (nearest_expiry - trade_dt).days

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
        "total_call_oi": call_oi,
        "total_put_oi": put_oi,
        "call_oi_chg": call_oi_chg,
        "put_oi_chg": put_oi_chg,
        "days_to_expiry": dte,
    }


def build_fno_dataset(dates):
    rows = []
    n = len(dates)
    for i, d in enumerate(dates):
        if (i + 1) % 25 == 0 or i == 0:
            print(f"  F&O fetch {i+1}/{n} ({d}) ...")
        df = fetch_fno_bhavcopy(d)
        feat = extract_nifty_features(df, d)
        if feat:
            rows.append(feat)
        time.sleep(0.15)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    price_df, vix = fetch_price_and_vix()
    price_features = build_price_features(price_df)
    print(f"Price feature rows: {len(price_features)}")

    dates = [str(d) for d in price_features["date"].tolist()]
    fno_df = build_fno_dataset(dates)
    print(f"F&O feature rows: {len(fno_df)}")

    price_features["date"] = price_features["date"].astype(str)
    fno_df["date"] = fno_df["date"].astype(str)

    merged = price_features.merge(fno_df, on="date", how="inner")
    merged["vix"] = merged["date"].map(lambda d: vix.get(pd.Timestamp(d).date(), np.nan))
    merged["fut_oi_chg_pct"] = merged["fut_oi_chg"] / (merged["fut_oi"] - merged["fut_oi_chg"] + 1e-9) * 100

    out_path = os.path.join(HERE, "master_dataset.csv")
    merged.to_csv(out_path, index=False)
    print(f"\nSaved master dataset: {len(merged)} rows -> {out_path}")
    print(merged.isna().sum())