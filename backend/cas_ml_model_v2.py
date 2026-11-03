"""
CAS ML model v2 — retrained on the EXPANDED dataset (master_dataset_v2.csv)
which adds cross-asset macro features (Bank Nifty, USD/INR, Crude oil, Dow
Jones, Global VIX — all lag1, no lookahead) on top of the original v1
feature set (F&O basis/OI/PCR, VIX, rolling volatility, prior closing moves).

Goal: determine whether the additional cross-asset data meaningfully
improves walk-forward out-of-sample accuracy vs the v1 model
(cas_ml_model.py: big-move F1=0.480, directional accuracy=60.5%).

Uses the SAME walk-forward validation methodology as v1 for a fair,
apples-to-apples comparison.
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
DATA_PATH = os.path.join(HERE, "master_dataset_v2.csv")


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

    df["prev_close_move"] = df["close_move_pct"].shift(1)
    df["prev_close_move2"] = df["close_move_pct"].shift(2)
    df["basis_change"] = df["fut_basis"].diff().shift(1)
    df["pcr_change"] = df["pcr"].diff().shift(1)
    df["is_expiry_day"] = (df["days_to_expiry"] <= 1).astype(int)

    dow_dummies = pd.get_dummies(df["day_of_week"], prefix="dow")
    df = pd.concat([df, dow_dummies], axis=1)

    df["target_big_move"] = (df["abs_close_move_pct"] >= df["abs_close_move_pct"].quantile(0.75)).astype(int)
    df["target_dir_up"] = (df["close_move_pct"] > 0).astype(int)

    # IMPORTANT: The Dow Jones cross-asset ticker's engineered columns
    # ("dow_chg_pct_lag1", "dow_close_lag1") accidentally share the "dow_"
    # prefix with the day-of-week one-hot dummy columns ("dow_Monday",
    # "dow_Tuesday", etc.). We must exclude the Dow-Jones columns from the
    # day-of-week sweep below, otherwise "dow_chg_pct_lag1" gets duplicated
    # in the final feature list (once via the sweep, once via
    # cross_asset_cols), which breaks df[feature_cols].values (produces a
    # ragged/2D-in-2D array instead of a clean 1D feature vector per row).
    dow_of_week_cols = [
        c for c in df.columns
        if c.startswith("dow_") and c not in ("dow_chg_pct_lag1", "dow_close_lag1")
    ]

    v1_feature_cols = [
        "fut_basis_lag1", "fut_oi_chg_pct_lag1", "fut_volume_lag1", "pcr_lag1",
        "call_oi_chg_lag1", "put_oi_chg_lag1", "vix_lag1", "days_to_expiry_lag1",
        "day_range_pct_lag1", "abs_main_move", "main_move_pct",
        "rolling5_abs_close_move", "rolling10_abs_close_move",
        "prev_close_move", "prev_close_move2", "basis_change", "pcr_change",
        "is_expiry_day",
    ] + dow_of_week_cols

    cross_asset_cols = [
        "banknifty_chg_pct_lag1", "usdinr_chg_pct_lag1", "crude_chg_pct_lag1",
        "dow_chg_pct_lag1", "global_vix_chg_pct_lag1", "global_vix_close_lag1",
    ]

    v2_feature_cols = v1_feature_cols + cross_asset_cols

    assert len(v2_feature_cols) == len(set(v2_feature_cols)), (
        f"Duplicate feature columns detected: "
        f"{[c for c in set(v2_feature_cols) if v2_feature_cols.count(c) > 1]}"
    )

    df_clean = df.dropna(subset=v2_feature_cols + ["target_big_move"]).reset_index(drop=True)
    return df_clean, v1_feature_cols, v2_feature_cols


def walk_forward_backtest(df, feature_cols, target_col, model_factory, min_train=150, step=10):
    n = len(df)
    all_preds, all_actuals, all_probs = [], [], []
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
    print(f"N: {len(actuals)}  Baseline: {baseline:.1%}")
    print(f"Accuracy: {acc:.1%}  Precision: {prec:.1%}  Recall: {rec:.1%}  F1: {f1:.3f}")
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
    df, v1_cols, v2_cols = load_and_engineer()
    print(f"Dataset: {len(df)} rows")
    print(f"v1 features: {len(v1_cols)}   v2 features (v1 + cross-asset): {len(v2_cols)}")

    model_factory_rf_big = lambda: RandomForestClassifier(n_estimators=300, max_depth=5, min_samples_leaf=8, random_state=42, class_weight="balanced")
    model_factory_rf_dir = lambda: RandomForestClassifier(n_estimators=300, max_depth=4, min_samples_leaf=10, random_state=42, class_weight="balanced")

    results = {}

    print("\n" + "#" * 80)
    print("BIG-MOVE DETECTION: v1 features vs v2 (v1 + cross-asset)")
    print("#" * 80)

    preds, actuals, probs = walk_forward_backtest(df, v1_cols, "target_big_move", model_factory_rf_big)
    best_t, _ = find_best_threshold(probs, actuals)
    tuned = (probs >= best_t).astype(int)
    results["big_move_v1"] = evaluate(tuned, actuals, f"v1 features only (threshold={best_t:.2f})")

    preds, actuals, probs = walk_forward_backtest(df, v2_cols, "target_big_move", model_factory_rf_big)
    best_t, _ = find_best_threshold(probs, actuals)
    tuned = (probs >= best_t).astype(int)
    results["big_move_v2"] = evaluate(tuned, actuals, f"v2 features (+cross-asset) (threshold={best_t:.2f})")

    print("\n" + "#" * 80)
    print("DIRECTIONAL PREDICTION: v1 features vs v2 (v1 + cross-asset)")
    print("#" * 80)

    preds, actuals, probs = walk_forward_backtest(df, v1_cols, "target_dir_up", model_factory_rf_dir)
    results["dir_v1"] = evaluate(preds, actuals, "v1 features only")

    preds, actuals, probs = walk_forward_backtest(df, v2_cols, "target_dir_up", model_factory_rf_dir)
    results["dir_v2"] = evaluate(preds, actuals, "v2 features (+cross-asset)")

    print("\n" + "=" * 80)
    print("SUMMARY: Did cross-asset features improve accuracy?")
    print("=" * 80)
    print(f"Big-move F1:      v1={results['big_move_v1']['f1']:.3f}  v2={results['big_move_v2']['f1']:.3f}  "
          f"({'IMPROVED' if results['big_move_v2']['f1'] > results['big_move_v1']['f1'] else 'NO IMPROVEMENT'})")
    print(f"Directional acc:  v1={results['dir_v1']['accuracy']:.1%}  v2={results['dir_v2']['accuracy']:.1%}  "
          f"({'IMPROVED' if results['dir_v2']['accuracy'] > results['dir_v1']['accuracy'] else 'NO IMPROVEMENT'})")

    with open(os.path.join(HERE, "cas_ml_v2_results.json"), "w") as f:
        json.dump(results, f, indent=2, default=float)
    print(f"\nSaved results to backend/cas_ml_v2_results.json")

    # Feature importance for v2 model (which cross-asset features matter most?)
    print("\n" + "=" * 80)
    print("Feature importance (v2 directional model, trained on full data)")
    print("=" * 80)
    X = df[v2_cols].values
    y = df["target_dir_up"].values
    model = model_factory_rf_dir()
    model.fit(X, y)
    importances = sorted(zip(v2_cols, model.feature_importances_), key=lambda x: -x[1])
    for name, imp in importances[:15]:
        marker = " <- CROSS-ASSET" if name in ["banknifty_chg_pct_lag1", "usdinr_chg_pct_lag1", "crude_chg_pct_lag1", "dow_chg_pct_lag1", "global_vix_chg_pct_lag1", "global_vix_close_lag1"] else ""
        print(f"  {name:30s} {imp:.4f}{marker}")