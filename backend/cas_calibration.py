"""
Probability calibration for the CAS signal models.

Raw RandomForest predict_proba() outputs are NOT well-calibrated probabilities
in general — e.g. a raw 0.60 doesn't necessarily mean a true 60% real-world
win rate. This module fits an Isotonic Regression calibrator on top of the
walk-forward (out-of-sample) predicted probabilities vs actual outcomes, so
that the live signal can report a genuine POP (Probability Of being correct /
Probability of Profit-direction) based on ACTUAL historical hit-rates at each
probability level — not just the raw, potentially over/under-confident model
score.

Usage:
    python3 cas_calibration.py     # fits + saves calibrators + prints table

Then cas_live_signal.py loads the saved calibrators and applies them to the
live raw model probabilities before presenting a "POP" to the user.
"""
import os
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import calibration_curve
import warnings
warnings.filterwarnings("ignore")

from cas_ml_model import load_and_engineer
from cas_ml_model_v2 import load_and_engineer as load_and_engineer_v2

HERE = os.path.dirname(__file__)
CALIB_DIR_PATH = os.path.join(HERE, "iso_calib_directional.pkl")
CALIB_BIG_PATH = os.path.join(HERE, "iso_calib_bigmove.pkl")
CALIB_META_PATH = os.path.join(HERE, "calibration_meta.json")


def walk_forward_probs(df, feature_cols, target_col, min_train=150, step=10,
                        n_estimators=300, max_depth=4, min_samples_leaf=10):
    """Same walk-forward scheme as cas_ml_model.py — returns raw
    out-of-sample probabilities + actual outcomes (no lookahead)."""
    n = len(df)
    all_actuals, all_probs = [], []
    i = min_train
    while i < n:
        train = df.iloc[:i]
        test = df.iloc[i:i + step]
        if len(test) == 0:
            break
        X_train = train[feature_cols].values
        y_train = train[target_col].values
        X_test = test[feature_cols].values
        y_test = test[target_col].values

        model = RandomForestClassifier(
            n_estimators=n_estimators, max_depth=max_depth,
            min_samples_leaf=min_samples_leaf, random_state=42, class_weight="balanced"
        )
        model.fit(X_train, y_train)
        probs = model.predict_proba(X_test)[:, 1]

        all_probs.extend(probs.tolist())
        all_actuals.extend(y_test.tolist())
        i += step

    return np.array(all_actuals), np.array(all_probs)


# Safety bounds: with only ~330 walk-forward samples, the isotonic fit can
# become overconfident (jump to 0% or 100%) in sparse tail regions where only
# 0-2 samples exist. We clip the final reported POP to a conservative range
# and separately report the sample count backing each region so users can
# judge reliability of extreme POP values.
POP_FLOOR = 0.05
POP_CEIL = 0.90


def _sample_count_near(probs, target_prob, window=0.05):
    return int(((probs >= target_prob - window) & (probs <= target_prob + window)).sum())


def fit_calibrators():
    # Big-move classifier uses v1 features (v2/cross-asset didn't improve it)
    df_big, feature_cols_big = load_and_engineer()
    # Directional classifier uses v2 features (v1 + cross-asset) since that
    # genuinely improved walk-forward accuracy (60.8% -> 62.0%)
    df_dir, _, feature_cols_dir = load_and_engineer_v2()

    print("Computing walk-forward out-of-sample probabilities for calibration...")
    actuals_dir, probs_dir = walk_forward_probs(
        df_dir, feature_cols_dir, "target_dir_up",
        n_estimators=300, max_depth=4, min_samples_leaf=10
    )
    actuals_big, probs_big = walk_forward_probs(
        df_big, feature_cols_big, "target_big_move",
        n_estimators=300, max_depth=5, min_samples_leaf=8
    )

    iso_dir = IsotonicRegression(out_of_bounds="clip", y_min=POP_FLOOR, y_max=POP_CEIL)
    iso_dir.fit(probs_dir, actuals_dir)

    iso_big = IsotonicRegression(out_of_bounds="clip", y_min=POP_FLOOR, y_max=POP_CEIL)
    iso_big.fit(probs_big, actuals_big)

    joblib.dump(iso_dir, CALIB_DIR_PATH)
    joblib.dump(iso_big, CALIB_BIG_PATH)

    # Report calibration curves for transparency, WITH sample counts so users
    # can see how much data backs each probability region (sparse tails =
    # less trustworthy POP estimates).
    test_vals = np.arange(0.1, 0.95, 0.05)
    dir_table = [
        {
            "raw_prob": round(float(v), 2),
            "calibrated_pop": round(float(iso_dir.predict([v])[0]), 3),
            "n_samples_nearby": _sample_count_near(probs_dir, v),
        }
        for v in test_vals
    ]
    big_table = [
        {
            "raw_prob": round(float(v), 2),
            "calibrated_pop": round(float(iso_big.predict([v])[0]), 3),
            "n_samples_nearby": _sample_count_near(probs_big, v),
        }
        for v in test_vals
    ]

    # Also compute standard reliability bins for a sanity check / report
    frac_pos_dir, mean_pred_dir = calibration_curve(actuals_dir, probs_dir, n_bins=5, strategy="quantile")
    frac_pos_big, mean_pred_big = calibration_curve(actuals_big, probs_big, n_bins=5, strategy="quantile")

    meta = {
        "n_directional_samples": len(actuals_dir),
        "n_bigmove_samples": len(actuals_big),
        "directional_calibration_table": dir_table,
        "bigmove_calibration_table": big_table,
        "directional_reliability_bins": [
            {"mean_predicted": round(float(mp), 3), "actual_rate": round(float(fp), 3)}
            for mp, fp in zip(mean_pred_dir, frac_pos_dir)
        ],
        "bigmove_reliability_bins": [
            {"mean_predicted": round(float(mp), 3), "actual_rate": round(float(fp), 3)}
            for mp, fp in zip(mean_pred_big, frac_pos_big)
        ],
    }
    with open(CALIB_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    print("\n=== Directional model calibration (raw -> true historical POP) ===")
    for row in dir_table:
        print(f"  raw={row['raw_prob']:.2f} -> POP={row['calibrated_pop']:.1%}")

    print("\n=== Big-move model calibration (raw -> true historical POP) ===")
    for row in big_table:
        print(f"  raw={row['raw_prob']:.2f} -> POP={row['calibrated_pop']:.1%}")

    print(f"\nSaved calibrators to {CALIB_DIR_PATH} and {CALIB_BIG_PATH}")
    print(f"Saved calibration report to {CALIB_META_PATH}")

    return iso_dir, iso_big


def load_calibrators():
    """Load pre-fit calibrators, fitting them first if missing."""
    if not (os.path.exists(CALIB_DIR_PATH) and os.path.exists(CALIB_BIG_PATH)):
        return fit_calibrators()
    iso_dir = joblib.load(CALIB_DIR_PATH)
    iso_big = joblib.load(CALIB_BIG_PATH)
    return iso_dir, iso_big


def calibrated_pop(raw_prob, model_type="directional"):
    """
    Convert a raw model probability into a calibrated POP (Probability Of
    being correct), based on actual historical walk-forward hit-rates.

    model_type: "directional" or "bigmove"
    """
    iso_dir, iso_big = load_calibrators()
    iso = iso_dir if model_type == "directional" else iso_big
    return float(iso.predict([raw_prob])[0])


if __name__ == "__main__":
    fit_calibrators()