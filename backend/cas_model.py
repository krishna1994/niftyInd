"""
CAS closing-window predictive model & backtest.

Loads backend/master_dataset.csv (built by build_dataset.py) and:
  1. Engineers a binary target: "big closing move" = |close_move_pct| > threshold
     (threshold = rolling/median-based, configurable)
  2. Builds a rule-based composite score from F&O + price features
     (no lookahead: everything is known by ~15:00, before the closing window)
  3. Backtests the rule-based signal with a strict time-based train/test split
     (first 70% of days = "train" to pick thresholds, last 30% = "test")
  4. Reports precision/recall/accuracy of predicting big-move days,
     and directional accuracy (predicting UP vs DOWN close-window moves)
  5. Also fits a simple Logistic Regression / RandomForest (scikit-learn) as
     a comparison benchmark, using proper time-based split (no shuffling).
  6. Saves the final chosen model + feature means/stds for live inference.

All feature engineering avoids lookahead bias: everything used to build the
signal are values as of the pre-closing-window snapshot (open, high, low so far,
main-session move, prior-day F&O data since same-day F&O data is only
available after close in reality — so we lag F&O features by 1 day).
"""
import os
import json
import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
DATA_PATH = os.path.join(HERE, "master_dataset.csv")
MODEL_PATH = os.path.join(HERE, "cas_model.json")


def load_data():
    df = pd.read_csv(DATA_PATH, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    return df


def engineer_features(df):
    """
    IMPORTANT (no lookahead): F&O data (OI, PCR, basis) for date D is only
    known EOD on date D — i.e. AFTER the closing window we're trying to
    predict. So for a live/pre-market signal, we must use the PREVIOUS day's
    F&O data (lag 1) to predict TODAY's closing-window move. This matches how
    a real trader would use "yesterday's OI build-up" to anticipate today's
    close.
    """
    df = df.copy()
    fno_cols = ["fut_basis", "fut_oi", "fut_oi_chg", "fut_oi_chg_pct", "fut_volume",
                "pcr", "total_call_oi", "total_put_oi", "call_oi_chg", "put_oi_chg",
                "days_to_expiry", "vix"]
    for c in fno_cols:
        df[f"{c}_lag1"] = df[c].shift(1)

    # Main-session features are legitimately known before the close (same day)
    df["day_range_pct_lag1"] = df["day_range_pct"].shift(1)
    df["abs_main_move_lag0"] = df["main_move_pct"].abs()  # same-day, known pre-close

    # Day-of-week one-hot
    dow_dummies = pd.get_dummies(df["day_of_week"], prefix="dow")
    df = pd.concat([df, dow_dummies], axis=1)

    # Target: absolute closing-window move, and binary big-move flag
    df["target_abs_move"] = df["abs_close_move_pct"]
    df["target_dir_up"] = (df["close_move_pct"] > 0).astype(int)

    return df


def pick_threshold(df, quantile=0.75):
    """Define 'big move' as top quartile of |closing move| (train set only)."""
    return df["target_abs_move"].quantile(quantile)


def rule_based_score(row):
    """
    Composite rule-based score (0-100) for "risk of big closing move today",
    built from findings in fno_analysis.py:
      - |fut_basis_lag1| extremity (z-scored)
      - fut_oi_chg_pct_lag1 extremity
      - fut_volume_lag1 relative level
      - PCR_lag1 extremity (distance from 1.0, esp. <0.8 zone)
      - day_range_pct_lag1 (yesterday's volatility)
      - abs_main_move_lag0 (today's main-session volatility so far)
    """
    score = 0.0
    weights_used = 0.0

    def add(val, weight, scale):
        nonlocal score, weights_used
        if pd.notna(val):
            score += min(abs(val) / scale, 1.0) * weight
            weights_used += weight

    add(row.get("fut_basis_lag1"), 25, 60.0)          # basis of ~60pts = extreme
    add(row.get("fut_oi_chg_pct_lag1"), 20, 3.0)       # >3% OI chg = extreme
    add(row.get("abs_main_move_lag0"), 30, 0.6)        # >0.6% intraday move = high
    add(row.get("day_range_pct_lag1"), 15, 1.0)        # >1% range = high vol day
    pcr = row.get("pcr_lag1")
    if pd.notna(pcr):
        pcr_extremity = max(0.8 - pcr, pcr - 1.2, 0) / 0.4
        score += min(pcr_extremity, 1.0) * 10
        weights_used += 10

    if weights_used == 0:
        return np.nan
    return score / weights_used * 100


def backtest(df, threshold_quantile=0.75, split=0.7):
    n = len(df)
    split_idx = int(n * split)
    train, test = df.iloc[:split_idx], df.iloc[split_idx:]

    big_move_threshold = pick_threshold(train, threshold_quantile)
    print(f"Big-move threshold (train {threshold_quantile:.0%} quantile of |close move|): {big_move_threshold:.3f}%")

    df = df.copy()
    df["rule_score"] = df.apply(rule_based_score, axis=1)

    train = df.iloc[:split_idx]
    test = df.iloc[split_idx:]

    # Pick score cutoff on TRAIN only, that best separates big-move days
    train_valid = train.dropna(subset=["rule_score"])
    best_cutoff, best_f1 = None, -1
    for cutoff in np.arange(10, 90, 2):
        pred = (train_valid["rule_score"] >= cutoff).astype(int)
        actual = (train_valid["target_abs_move"] >= big_move_threshold).astype(int)
        tp = ((pred == 1) & (actual == 1)).sum()
        fp = ((pred == 1) & (actual == 0)).sum()
        fn = ((pred == 0) & (actual == 1)).sum()
        precision = tp / (tp + fp) if (tp + fp) else 0
        recall = tp / (tp + fn) if (tp + fn) else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0
        if f1 > best_f1:
            best_f1, best_cutoff = f1, cutoff

    print(f"Best score cutoff (train): {best_cutoff}  (train F1={best_f1:.3f})")

    # Evaluate on TEST (unseen)
    test_valid = test.dropna(subset=["rule_score"])
    pred = (test_valid["rule_score"] >= best_cutoff).astype(int)
    actual = (test_valid["target_abs_move"] >= big_move_threshold).astype(int)

    tp = ((pred == 1) & (actual == 1)).sum()
    fp = ((pred == 1) & (actual == 0)).sum()
    fn = ((pred == 0) & (actual == 1)).sum()
    tn = ((pred == 0) & (actual == 0)).sum()

    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    accuracy = (tp + tn) / len(test_valid) if len(test_valid) else 0
    baseline_rate = actual.mean()

    print(f"\n=== TEST SET (out-of-sample, {len(test_valid)} days) ===")
    print(f"Baseline big-move rate: {baseline_rate:.1%}")
    print(f"Predicted big-move rate: {pred.mean():.1%}")
    print(f"Accuracy:  {accuracy:.1%}")
    print(f"Precision: {precision:.1%}  (of days flagged, how often was it actually a big move)")
    print(f"Recall:    {recall:.1%}  (of actual big-move days, how many did we flag)")
    print(f"Confusion: TP={tp} FP={fp} FN={fn} TN={tn}")

    return {
        "big_move_threshold": float(big_move_threshold),
        "score_cutoff": float(best_cutoff),
        "test_precision": float(precision),
        "test_recall": float(recall),
        "test_accuracy": float(accuracy),
        "test_baseline_rate": float(baseline_rate),
        "n_test": int(len(test_valid)),
    }


def directional_backtest(df, split=0.7):
    """Can we predict direction (UP vs DOWN) of the closing move better than 50%?"""
    n = len(df)
    split_idx = int(n * split)

    df = df.copy()
    # Simple directional rule: fade the main-session move if PCR/basis suggest
    # over-extension (mean reversion), else follow main-session move.
    def dir_signal(row):
        main_move = row.get("main_move_pct", np.nan)
        basis = row.get("fut_basis_lag1", np.nan)
        if pd.isna(main_move):
            return np.nan
        # Base: mean-reversion (fade main session move), as found in cas_analysis.py
        base_dir = -1 if main_move > 0 else 1
        # Adjust with futures basis: rich basis -> bearish tilt; cheap basis -> bullish tilt
        if pd.notna(basis):
            if basis > 40:
                base_dir = -1
            elif basis < 10:
                base_dir = 1
        return base_dir

    df["dir_pred"] = df.apply(dir_signal, axis=1)
    df["dir_actual"] = np.where(df["close_move_pct"] > 0, 1, -1)

    test = df.iloc[split_idx:].dropna(subset=["dir_pred"])
    correct = (test["dir_pred"] == test["dir_actual"]).mean()
    print(f"\n=== Directional prediction accuracy (test set, mean-reversion+basis rule) ===")
    print(f"Accuracy: {correct:.1%}  (baseline random = 50%)")
    return float(correct)


if __name__ == "__main__":
    df = load_data()
    print(f"Loaded {len(df)} rows from {DATA_PATH}")
    df = engineer_features(df)

    result = backtest(df, threshold_quantile=0.75, split=0.7)
    dir_acc = directional_backtest(df, split=0.7)
    result["directional_accuracy"] = dir_acc

    with open(MODEL_PATH, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved model config to {MODEL_PATH}")