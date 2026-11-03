"""
CAS (Closing Auction / Call-Auction Session) end-of-day movement analysis.

Fetches intraday Nifty 5-minute data (yfinance limits 5m history to ~60 days),
splits each trading day into:
  - "Main session" candles  (09:15 - 15:00 IST)
  - "Closing window" candles (15:00 - 15:30 IST)  <- proxy for CAS-affected period

For each day it computes:
  - close-window % move (net directional change in last 30 min)
  - close-window range (high-low as % of day's range) -> volatility spike
  - main-session % move (open to 15:00)
  - main-session ATR / range
  - day-of-week (weekly Nifty expiry = Thursday)
  - whether closing-window move is same direction as main-session trend,
    or a reversal (mean reversion vs momentum continuation)

Then aggregates stats to look for a predictive pattern.
"""
import yfinance as yf
import pandas as pd
import numpy as np

IST_OFFSET = pd.Timedelta(hours=5, minutes=30)


def fetch_intraday(period="60d", interval="5m"):
    df = yf.download("^NSEI", period=period, interval=interval, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).strip() for c in df.columns]
    df = df[["Open", "High", "Low", "Close"]].copy()

    # Convert UTC index -> IST
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert("Asia/Kolkata")
    df["date"] = df.index.date
    df["time"] = df.index.time
    return df


def analyze_days(df):
    rows = []
    for day, g in df.groupby("date"):
        g = g.sort_index()
        if len(g) < 5:
            continue

        day_open = g["Open"].iloc[0]
        day_high = g["High"].max()
        day_low = g["Low"].min()
        day_range = day_high - day_low
        if day_range == 0:
            continue

        # Closing window = last 30 minutes of trading (15:00 - 15:30 IST)
        close_window = g[g["time"] >= pd.Timestamp("15:00").time()]
        main_session = g[g["time"] < pd.Timestamp("15:00").time()]

        if close_window.empty or main_session.empty:
            continue

        main_start_close = main_session["Close"].iloc[0]
        main_end_close = main_session["Close"].iloc[-1]
        day_final_close = close_window["Close"].iloc[-1]

        main_move_pct = (main_end_close - main_start_close) / main_start_close * 100
        close_move_pct = (day_final_close - main_end_close) / main_end_close * 100

        close_window_range = close_window["High"].max() - close_window["Low"].min()
        close_range_pct_of_day = (close_window_range / day_range) * 100

        main_trend = "UP" if main_move_pct > 0 else ("DOWN" if main_move_pct < 0 else "FLAT")
        close_trend = "UP" if close_move_pct > 0 else ("DOWN" if close_move_pct < 0 else "FLAT")
        reversal = (main_trend != close_trend) and main_trend != "FLAT" and close_trend != "FLAT"

        dow = pd.Timestamp(day).day_name()

        rows.append({
            "date": day,
            "day_of_week": dow,
            "main_move_pct": main_move_pct,
            "close_move_pct": close_move_pct,
            "abs_close_move_pct": abs(close_move_pct),
            "close_range_pct_of_day": close_range_pct_of_day,
            "main_trend": main_trend,
            "close_trend": close_trend,
            "is_reversal": reversal,
        })

    return pd.DataFrame(rows)


def summarize(results):
    print(f"\nTotal trading days analyzed: {len(results)}")
    print(f"Date range: {results['date'].min()} to {results['date'].max()}\n")

    print("=== Closing-window (last 30 min) move statistics ===")
    print(results["close_move_pct"].describe())

    print("\n=== Avg |closing move| by day of week (weekly expiry = Thursday) ===")
    print(results.groupby("day_of_week")["abs_close_move_pct"].agg(["mean", "count"]).sort_values("mean", ascending=False))

    print("\n=== Closing-window range as % of full day range, by day of week ===")
    print(results.groupby("day_of_week")["close_range_pct_of_day"].mean().sort_values(ascending=False))

    reversal_rate = results["is_reversal"].mean() * 100
    print(f"\n=== Reversal rate (closing move opposite to main-session trend): {reversal_rate:.1f}% ===")

    print("\n=== Correlation: main_move_pct vs close_move_pct (trend continuation vs reversal) ===")
    corr = results["main_move_pct"].corr(results["close_move_pct"])
    print(f"correlation = {corr:.3f}  (negative => mean-reversion tendency into close, positive => momentum continuation)")

    # Days with largest closing moves
    print("\n=== Top 10 largest closing-window moves ===")
    top = results.reindex(results["abs_close_move_pct"].sort_values(ascending=False).index).head(10)
    print(top[["date", "day_of_week", "main_move_pct", "close_move_pct", "close_range_pct_of_day"]].to_string(index=False))

    # Simple predictive check: does high main-session volatility (range) predict large closing move?
    print("\n=== Does a big main-session move predict a big closing-window move? ===")
    corr_abs = results["main_move_pct"].abs().corr(results["abs_close_move_pct"])
    print(f"correlation(|main move|, |closing move|) = {corr_abs:.3f}")


if __name__ == "__main__":
    df = fetch_intraday()
    results = analyze_days(df)
    summarize(results)
    results.to_csv("cas_analysis_output.csv", index=False)
    print("\nSaved per-day results to backend/cas_analysis_output.csv")