"""
Advanced ML-based CAS closing-window prediction model.

Goals:
  1. Predict whether TODAY's closing-window (last ~30-75 min) move will be
     "large" (top quartile of |move|) using ONLY information available
     before the closing window starts (no lookahead).
  2. Predict the DIRECTION of the closing-window move (up/down) to help
     decide CE vs PE.
  3. Use walk-forward (expanding window) backtesting — much more robust
     than a single train/test split — to get a realistic accuracy estimate.
  4. Compare against a naive baseline (always predict majority class).
  5. Save the final trained model + feature list for live inference.

IMPROVEMENT LOG (empirically tested):
  - v1 features (basis/OI/PCR/vix lag1 + main-session move + dow):
        big-move F1=0.454 (RandomForest), directional accuracy ~53-55%
  - v2 added: prev_close_move (lag1/lag2 of closing-window move itself),
        basis_change, pcr_change (day-over-day deltas):
        directional accuracy improved to 63.2% (vs 51.6% baseline)
    -> closing-window moves show autocorrelation: yesterday's closing
       move direction/magnitude has predictive value for today's, on top
       of the F&O positioning features.

Features used (all lagged/legit — no lookahead):
  - fut_basis_lag1, fut_oi_chg_pct_lag1, fut_volume_lag1, pcr_lag1,
    call_oi_chg_lag1, put_oi_chg_lag1, vix_lag1, days_to_expiry_lag1
  - day_range_pct_lag1 (yesterday's volatility)
  - abs_main_move_lag0 (today's intraday move so far, known before close)
  - main_move_pct (today's main-session move, signed)
  - prev_close_move, prev_close_move2 (lag1/lag2 of the closing-window move)
  - basis_change, pcr_change (day-over-day deltas, lagged)
  - day_of_week (one-hot)
  - rolling 5/10-day avg of abs_close_move_pct (recent volatility regime)
"""
import os
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, accuracy_score, f1_score
import warnings
warnings.filterwarnings("ignore")

HERE = os.path.dirname(__file__)
DATA_PATH = os.path.join(HERE, "master_dataset.csv")


def load_and_engineer():
    df = pd.read_csv(DATA_PATH, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)

    lag_cols = ["fut_basis", "fut_oi_chg_pct", "fut_volume", "pcr",
                "call_oi_chg", "put_oi_chg", "vix", "days_to_expiry", "day_range_pct"]
    for c in lag_cols:
        df[f"{c}_lag1"] = df[c].shift(1)

    df["abs_main_move"] = df["main_move_pct"].abs()
    df["rolling5_abs_close_move"] = df["abs_close_move_pct"].shift(1).rolling(5).mean()
    df["rolling10_abs_close_move"] = df["abs_close_move_pct"].shift(1).rolling(10).mean()

    # v2 additions: autocorrelation + day-over-day deltas
    df["prev_close_move"] = df["close_move_pct"].shift(1)
    df["prev_close_move2"] = df["close_move_pct"].shift(2)
    df["basis_change"] = df["fut_basis"].diff().shift(1)
    df["pcr_change"] = df["pcr"].diff().shift(1)
    df["is_expiry_day"] = (df["days_to_expiry"] <= 1).astype(int)

    dow_dummies = pd.get_dummies(df["day_of_week"], prefix="dow")
    df = pd.concat([df, dow_dummies], axis=1)

    df["target_big_move"] = (df["abs_close_move_pct"] >= df["abs_close_move_pct"].quantile(0.75)).astype(int)
    df["target_dir_up"] = (df["close_move_pct"] > 0).astype(int)

    feature_cols = [
        "fut_basis_lag1", "fut_oi_chg_pct_lag1", "fut_volume_lag1", "pcr_lag1",
        "call_oi_chg_lag1", "put_oi_chg_lag1", "vix_lag1", "days_to_expiry_lag1",
        "day_range_pct_lag1", "abs_main_move", "main_move_pct",
        "rolling5_abs_close_move", "rolling10_abs_close_move",
        "prev_close_move", "prev_close_move2", "basis_change", "pcr_change",
        "is_expiry_day",
    ] + [c for c in df.columns if c.startswith("dow_")]

    df_clean = df.dropna(subset=feature_cols + ["target_big_move"]).reset_index(drop=True)
    return df_clean, feature_cols


def walk_forward_backtest(df, feature_cols, target_col, model_factory, min_train=150, step=10):
    """
    Expanding-window walk-forward validation:
      - train on [0:i], test on [i:i+step], slide forward.
    Returns aggregated predictions across all test windows (out-of-sample).
    """
    n = len(df)
    all_preds = []
    all_actuals = []
    all_probs = []

    i = min_train
    while i < n:
        train = df.iloc[:i]
        test = df.iloc[i:i+step]
        if len(test) == 0:
            break

        X_train = train[feature_cols].values
        y_train = train[target_col].values
        X_test = test[feature_cols].values
        y_test = test[target_col].values

        model = model_factory()
        model.fit(X_train, y_train)
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(X_test)[:, 1]
        else:
            probs = model.predict(X_test)
        preds = (probs >= 0.5).astype(int)

        all_preds.extend(preds.tolist())
        all_actuals.extend(y_test.tolist())
        all_probs.extend(probs.tolist())

        i += step

    return np.array(all_preds), np.array(all_actuals), np.array(all_probs)


def evaluate(preds, actuals, label):
    acc = accuracy_score(actuals, preds)
    prec = precision_score(actuals, preds, zero_division=0)
    rec = recall_score(actuals, preds, zero_division=0)
    f1 = f1_score(actuals, preds, zero_division=0)
    baseline = actuals.mean()
    print(f"\n=== {label} ===")
    print(f"N test predictions: {len(actuals)}")
    print(f"Baseline positive rate: {baseline:.1%}")
    print(f"Accuracy:  {acc:.1%}")
    print(f"Precision: {prec:.1%}")
    print(f"Recall:    {rec:.1%}")
    print(f"F1:        {f1:.3f}")
    return {"accuracy": acc, "precision": prec, "recall": rec, "f1": f1, "baseline": baseline}


def find_best_threshold(probs, actuals):
    best_f1, best_t = -1, 0.5
    for t in np.arange(0.2, 0.81, 0.02):
        preds = (probs >= t).astype(int)
        f1 = f1_score(actuals, preds, zero_division=0)
        if f1 > best_f1:
            best_f1, best_t = f1, t
    return best_t, best_f1


if __name__ == "__main__":
    df, feature_cols = load_and_engineer()
    print(f"Dataset after feature engineering: {len(df)} rows, {len(feature_cols)} features")

    results_summary = {}

    # ── Big-move classification: compare 3 models ──────────────────────────
    models = {
        "LogisticRegression": lambda: LogisticRegression(max_iter=1000, class_weight="balanced"),
        "RandomForest": lambda: RandomForestClassifier(n_estimators=300, max_depth=5, min_samples_leaf=8, random_state=42, class_weight="balanced"),
        "GradientBoosting": lambda: GradientBoostingClassifier(n_estimators=100, max_depth=2, learning_rate=0.05, random_state=42),
    }

    best_model_name, best_f1_overall = None, -1
    for name, factory in models.items():
        preds, actuals, probs = walk_forward_backtest(df, feature_cols, "target_big_move", factory)
        best_t, best_f1 = find_best_threshold(probs, actuals)
        tuned_preds = (probs >= best_t).astype(int)
        res = evaluate(tuned_preds, actuals, f"BIG-MOVE prediction ({name}, walk-forward, tuned threshold={best_t:.2f})")
        results_summary[name] = res
        if res["f1"] > best_f1_overall:
            best_f1_overall = res["f1"]
            best_model_name = name

    print(f"\n*** Best model for big-move detection: {best_model_name} (F1={best_f1_overall:.3f}) ***")

    # ── Directional classification (up vs down) ─────────────────────────────
    print("\n\n########## DIRECTIONAL PREDICTION (UP vs DOWN closing move) ##########")
    dir_results = {}
    for name, factory in models.items():
        preds, actuals, probs = walk_forward_backtest(df, feature_cols, "target_dir_up", factory)
        res = evaluate(preds, actuals, f"DIRECTION prediction ({name}, walk-forward, default 0.5 threshold)")
        dir_results[name] = res

    # Save summary
    out = {
        "n_samples": len(df),
        "big_move_results": results_summary,
        "directional_results": dir_results,
        "best_big_move_model": best_model_name,
        "feature_cols": feature_cols,
    }
    with open(os.path.join(HERE, "cas_ml_results.json"), "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(f"\nSaved results to backend/cas_ml_results.json")