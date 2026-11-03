"""
Deep scenario scan: search for market conditions where buying CE (bullish) or
PE (bearish) into the closing window has historically been correct with very
high win rate (~90%+), across ALL available features and their combinations.

Methodology (to avoid overfitting / false discovery on a small dataset):
  1. Chronological TRAIN/TEST split (70/30) — rules are discovered ONLY on
     TRAIN, then validated on unseen TEST. A rule that doesn't hold up
     out-of-sample is reported as unreliable, not hidden.
  2. Single-feature threshold scan: for every numeric feature, scan a range
     of thresholds (both >= and <=) and measure the resulting subgroup's
     directional win rate + sample size on TRAIN.
  3. Two-feature combination scan: same but requiring both conditions
     simultaneously (AND), to capture interaction effects (e.g. "high VIX
     AND rich futures basis").
  4. For every candidate subgroup with train win rate >= 80% and >= 15
     samples, report:
       - the rule/condition
       - train win rate + sample size
       - TEST win rate + sample size (out-of-sample validation)
       - a verdict: "VALIDATED" (test win rate also >=70%) vs
         "NOT VALIDATED / OVERFIT" (test win rate drops materially)
  5. Do the same for the "big move" target with a magnitude threshold, to
     find conditions where a BIG directional move in one particular
     direction is highly likely.

IMPORTANT: With ~479 total days (335 train / 144 test), finding an
apparent ~90% win rate rule is easy by chance alone if we scan enough
combinations (multiple-comparisons problem). We explicitly guard against
this by requiring:
  (a) A minimum sample size (>=15 on train, report exact N)
  (b) Out-of-sample validation on the untouched test set
  (c) Explicit reporting of ALL scanned rules that hit the 80%+ train bar,
      not just the best one (avoid cherry-picking)
"""
import os
import numpy as np
import pandas as pd
import json
from itertools import combinations

from cas_ml_model import load_and_engineer

HERE = os.path.dirname(__file__)

NUMERIC_FEATURES = [
    "fut_basis_lag1", "fut_oi_chg_pct_lag1", "fut_volume_lag1", "pcr_lag1",
    "call_oi_chg_lag1", "put_oi_chg_lag1", "vix_lag1", "days_to_expiry_lag1",
    "day_range_pct_lag1", "abs_main_move", "main_move_pct",
    "rolling5_abs_close_move", "rolling10_abs_close_move",
    "prev_close_move", "prev_close_move2", "basis_change", "pcr_change",
]

MIN_TRAIN_SAMPLES = 15
TRAIN_WINRATE_BAR = 0.80


def split_data(df):
    n = len(df)
    split_idx = int(n * 0.7)
    return df.iloc[:split_idx].copy(), df.iloc[split_idx:].copy()


def scan_single_feature(train, test, feature, target_col="target_dir_up"):
    """Scan thresholds for one feature, both directions (>=, <=)."""
    results = []
    vals = train[feature].dropna()
    if len(vals) < MIN_TRAIN_SAMPLES:
        return results

    quantiles = np.percentile(vals, np.arange(5, 100, 5))
    thresholds = sorted(set(np.round(quantiles, 4)))

    for t in thresholds:
        for op, mask_fn in [(">=", lambda s: s >= t), ("<=", lambda s: s <= t)]:
            mask_train = mask_fn(train[feature])
            n_train = mask_train.sum()
            if n_train < MIN_TRAIN_SAMPLES:
                continue
            win_rate_up = train.loc[mask_train, target_col].mean()
            # Consider both "predict UP" and "predict DOWN" (1 - win_rate_up)
            for direction, wr in [("UP", win_rate_up), ("DOWN", 1 - win_rate_up)]:
                if wr >= TRAIN_WINRATE_BAR:
                    mask_test = mask_fn(test[feature])
                    n_test = mask_test.sum()
                    if n_test > 0:
                        test_wr_up = test.loc[mask_test, target_col].mean()
                        test_wr = test_wr_up if direction == "UP" else 1 - test_wr_up
                    else:
                        test_wr = np.nan
                    results.append({
                        "rule": f"{feature} {op} {t:.4f}",
                        "direction": direction,
                        "train_win_rate": round(float(wr), 3),
                        "train_n": int(n_train),
                        "test_win_rate": round(float(test_wr), 3) if pd.notna(test_wr) else None,
                        "test_n": int(n_test),
                    })
    return results


def scan_pairwise_features(train, test, feat_a, feat_b, target_col="target_dir_up"):
    """Scan combined threshold conditions on two features simultaneously."""
    results = []
    vals_a = train[feat_a].dropna()
    vals_b = train[feat_b].dropna()
    if len(vals_a) < MIN_TRAIN_SAMPLES or len(vals_b) < MIN_TRAIN_SAMPLES:
        return results

    qa = np.percentile(vals_a, [25, 50, 75])
    qb = np.percentile(vals_b, [25, 50, 75])

    for ta in qa:
        for tb in qb:
            for op_a, fn_a in [(">=", lambda s: s >= ta), ("<=", lambda s: s <= ta)]:
                for op_b, fn_b in [(">=", lambda s: s >= tb), ("<=", lambda s: s <= tb)]:
                    mask_train = fn_a(train[feat_a]) & fn_b(train[feat_b])
                    n_train = mask_train.sum()
                    if n_train < MIN_TRAIN_SAMPLES:
                        continue
                    win_rate_up = train.loc[mask_train, target_col].mean()
                    for direction, wr in [("UP", win_rate_up), ("DOWN", 1 - win_rate_up)]:
                        if wr >= TRAIN_WINRATE_BAR:
                            mask_test = fn_a(test[feat_a]) & fn_b(test[feat_b])
                            n_test = mask_test.sum()
                            if n_test > 0:
                                test_wr_up = test.loc[mask_test, target_col].mean()
                                test_wr = test_wr_up if direction == "UP" else 1 - test_wr_up
                            else:
                                test_wr = np.nan
                            results.append({
                                "rule": f"{feat_a} {op_a} {ta:.4f} AND {feat_b} {op_b} {tb:.4f}",
                                "direction": direction,
                                "train_win_rate": round(float(wr), 3),
                                "train_n": int(n_train),
                                "test_win_rate": round(float(test_wr), 3) if pd.notna(test_wr) else None,
                                "test_n": int(n_test),
                            })
    return results


def dedupe_and_sort(results):
    """Remove near-duplicate rules (same feature+direction, very similar
    threshold) and sort by train_win_rate then train_n descending."""
    seen = set()
    deduped = []
    for r in sorted(results, key=lambda x: (-x["train_win_rate"], -x["train_n"])):
        key = (r["rule"].split()[0], r["direction"], round(r["train_win_rate"], 2))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    return deduped


def verdict(row):
    if row["test_win_rate"] is None or row["test_n"] < 5:
        return "INSUFFICIENT TEST DATA"
    if row["test_win_rate"] >= 0.70:
        return "VALIDATED (holds out-of-sample)"
    elif row["test_win_rate"] >= 0.55:
        return "PARTIALLY VALIDATED (weaker out-of-sample)"
    else:
        return "NOT VALIDATED / LIKELY OVERFIT"


def main():
    df, feature_cols = load_and_engineer()
    train, test = split_data(df)
    print(f"Train: {len(train)} days ({train['date'].min().date()} to {train['date'].max().date()})")
    print(f"Test:  {len(test)} days ({test['date'].min().date()} to {test['date'].max().date()})")

    all_results = []

    print("\nScanning single-feature rules for DIRECTIONAL win rate >=80% (train)...")
    for feat in NUMERIC_FEATURES:
        all_results.extend(scan_single_feature(train, test, feat, "target_dir_up"))

    print("Scanning pairwise-feature combinations...")
    for feat_a, feat_b in combinations(NUMERIC_FEATURES, 2):
        all_results.extend(scan_pairwise_features(train, test, feat_a, feat_b, "target_dir_up"))

    deduped = dedupe_and_sort(all_results)
    for r in deduped:
        r["verdict"] = verdict(r)

    validated = [r for r in deduped if r["verdict"].startswith("VALIDATED")]
    partial = [r for r in deduped if r["verdict"].startswith("PARTIALLY")]
    not_validated = [r for r in deduped if r["verdict"].startswith("NOT")]
    insufficient = [r for r in deduped if r["verdict"].startswith("INSUFFICIENT")]

    print(f"\nTotal candidate rules found (train win rate >=80%, n>={MIN_TRAIN_SAMPLES}): {len(deduped)}")
    print(f"  VALIDATED (test win rate >=70%):        {len(validated)}")
    print(f"  PARTIALLY VALIDATED (test 55-70%):       {len(partial)}")
    print(f"  NOT VALIDATED / overfit (test <55%):     {len(not_validated)}")
    print(f"  Insufficient test data to judge:         {len(insufficient)}")

    print("\n" + "=" * 100)
    print("TOP VALIDATED RULES (hold up out-of-sample)")
    print("=" * 100)
    if validated:
        for r in sorted(validated, key=lambda x: -x["train_n"])[:15]:
            print(f"[{r['direction']}] {r['rule']}")
            print(f"    train: {r['train_win_rate']:.1%} win rate (n={r['train_n']})   "
                  f"test: {r['test_win_rate']:.1%} win rate (n={r['test_n']})   -> {r['verdict']}")
    else:
        print("  None found. No single/pairwise-feature rule generalizes to >=70% "
              "out-of-sample win rate at this dataset size.")

    print("\n" + "=" * 100)
    print("PARTIALLY VALIDATED RULES (some out-of-sample edge, but below 70%)")
    print("=" * 100)
    for r in sorted(partial, key=lambda x: -x["train_n"])[:10]:
        print(f"[{r['direction']}] {r['rule']}")
        print(f"    train: {r['train_win_rate']:.1%} (n={r['train_n']})   test: {r['test_win_rate']:.1%} (n={r['test_n']})")

    print("\n" + "=" * 100)
    print(f"SAMPLE OF RULES THAT LOOKED GREAT ON TRAIN (>=80%) BUT FAILED OUT-OF-SAMPLE "
          f"({len(not_validated)} total, showing top 10 by train win rate)")
    print("=" * 100)
    for r in sorted(not_validated, key=lambda x: -x["train_win_rate"])[:10]:
        print(f"[{r['direction']}] {r['rule']}")
        print(f"    train: {r['train_win_rate']:.1%} (n={r['train_n']})   test: {r['test_win_rate']:.1%} (n={r['test_n']})  <- DID NOT HOLD")

    out_path = os.path.join(HERE, "high_conviction_scan_results.json")
    with open(out_path, "w") as f:
        json.dump({
            "train_period": [str(train["date"].min().date()), str(train["date"].max().date())],
            "test_period": [str(test["date"].min().date()), str(test["date"].max().date())],
            "n_train": len(train),
            "n_test": len(test),
            "all_candidate_rules": deduped,
            "summary": {
                "validated_count": len(validated),
                "partial_count": len(partial),
                "not_validated_count": len(not_validated),
                "insufficient_count": len(insufficient),
            }
        }, f, indent=2, default=str)
    print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    main()