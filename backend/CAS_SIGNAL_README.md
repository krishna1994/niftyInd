# CAS Closing-Window Signal System — Documentation

## Overview

This system predicts end-of-day "sudden movement" behavior in Nifty caused by
NSE's Closing Auction Session (CAS) mechanism, and suggests a directional
options trade (BUY CE / BUY PE) with a specific strike.

## Pipeline / Files

| File | Purpose |
|---|---|
| `build_dataset.py` | Builds `master_dataset.csv`: merges 60-min intraday Nifty price data (yfinance, ~2yr/492 trading days), daily India VIX, and NSE F&O bhavcopy (futures OI/basis/volume, options PCR/OI) for each day. |
| `master_dataset.csv` | The master historical dataset (492 rows, one per trading day). |
| `build_dataset_v2.py` | **Data expansion**: enriches `master_dataset.csv` with 5 lagged cross-asset macro features (Bank Nifty, USD/INR, Crude oil, Dow Jones, Global VIX) → `master_dataset_v2.csv`. Since 60-min intraday history is hard-capped at ~2 years by Yahoo Finance, this was the practical way to add more predictive signal per existing day rather than more days. |
| `master_dataset_v2.csv` | v1 dataset + 10 cross-asset columns (35 total columns, still 492 rows). |
| `fno_cache/` | Cached raw NSE F&O bhavcopy CSVs (avoids re-downloading). |
| `cas_ml_model.py` | v1 feature engineering + walk-forward backtest (big-move detector — best model, no improvement from cross-asset data). |
| `cas_ml_model_v2.py` | v2 feature engineering (v1 + cross-asset) + apples-to-apples walk-forward comparison vs v1. **Directional model uses this** — cross-asset features improved accuracy 60.8%→62.0%, precision 62.5%→64.9%. |
| `cas_analysis.py` / `fno_analysis.py` / `cas_model.py` | Earlier exploratory analysis scripts (price-only, then +F&O correlation, then first rule-based backtest). Kept for reference/history of the analysis process. |
| `nse_options.py` | Live NSE option-chain fetcher (uses the `option-chain-v3` endpoint — NSE's internal API path as of this build; may change again in future and require updating). |
| `cas_calibration.py` | Fits isotonic-regression calibrators that convert raw model probabilities into a genuine, historically-grounded **POP** (Probability Of being correct). Run standalone (`python3 cas_calibration.py`) to refresh calibration after retraining, or it auto-fits on first use. |
| `cas_live_signal.py` | **Main entry point.** Trains models on full history, fetches live spot/VIX/F&O/option-chain data, and outputs a live signal + suggested strike + calibrated POP. |
| `live_signal_output.json` | Output of the most recent live signal run. |
| `iso_calib_directional.pkl` / `iso_calib_bigmove.pkl` | Saved isotonic calibration models (binary, loaded automatically by `cas_live_signal.py`). |
| `calibration_meta.json` | Human-readable calibration report: raw-probability -> POP lookup tables + reliability bins + sample counts backing each region. |

## How to run

```bash
# Rebuild the historical dataset (only needed occasionally / to extend history)
python3 backend/build_dataset.py

# Re-run backtests (optional, for research/validation)
python3 backend/cas_ml_model.py

# Generate a live trading signal (run this daily, ideally in the afternoon
# before the ~15:00 closing window)
python3 backend/cas_live_signal.py
```

## What the signal contains

```json
{
  "big_move_probability": 0.617,
  "big_move_pop": 0.611,
  "risk_level": "HIGH",
  "directional_bias": "BULLISH",
  "directional_confidence": 0.69,
  "directional_pop": 0.688,
  "suggested_action": "BUY CE (Call)",
  "suggested_strike": 24200,
  "reasoning": [...],
  "pcr": 0.78,
  "max_pain": 24200,
  ...
}
```

## POP (Probability Of being correct) — what it is and why it matters

Raw model outputs (`predict_proba()`) from RandomForest/GradientBoosting are
**not automatically well-calibrated probabilities**. A raw score of "70%
confidence" doesn't necessarily mean the model is actually right 70% of the
time — it could be systematically over- or under-confident.

**POP fixes this** by applying **isotonic regression calibration**
(`cas_calibration.py`) fit on the model's walk-forward, out-of-sample
predictions vs. their actual historical outcomes. The result: `directional_pop`
and `big_move_pop` report the **real historical hit-rate** observed whenever
the model was this confident in the past — not just the raw model score.

Example interpretation of the sample output above:
- `directional_confidence: 0.69` (raw model score) → `directional_pop: 0.688`
  (calibrated) — in this case they're close, meaning the raw score was already
  fairly well-calibrated in this confidence range.
- `big_move_probability: 0.617` (raw) → `big_move_pop: 0.611` (calibrated) —
  again fairly close, but at more extreme raw scores the calibrated POP can
  diverge significantly from the raw score (see the calibration table below).

**Calibration table** (raw model probability → calibrated POP), computed from
`calibration_meta.json`:

| Raw probability | Directional POP | Big-move POP |
|---|---|---|
| 0.30 | 25.0% | 14.0% |
| 0.40 | 32.9% | 19.7% |
| 0.50 | 59.4% | 27.0% |
| 0.60 | 66.7% | 41.0% |
| 0.70 | 73.3% | 61.1% |
| 0.80+ | 90.0% (capped) | 90.0% (capped) |

Note: POP is **capped to a 5%–90% range**. This is deliberate — with only
~330 out-of-sample walk-forward test points, the extreme tails (raw ≥0.75 or
≤0.15) are backed by very few historical samples (sometimes 0-2), so an
uncapped isotonic fit would report overconfident 0%/100% POP values that
aren't statistically trustworthy. `calibration_meta.json` includes an
`n_samples_nearby` count for each probability bucket so you can see exactly
how much historical evidence backs any given POP estimate.

## HONEST performance summary (walk-forward, out-of-sample, no lookahead)

Backtested on 492 historical trading days using **expanding-window walk-forward
validation** (train on all data up to day N, predict day N+1..N+10, slide
forward — never trained on future data):

| Model | Feature set | Task | Accuracy | Precision | Recall | Baseline |
|---|---|---|---|---|---|---|
| RandomForest | v1 | Big-move detection (top-quartile \|closing move\|) | 67.5% | 37.6% | 67.6% | 22.5% |
| RandomForest | v2 (+ cross-asset) | Big-move detection | 67.8% | 36.9% | 60.8% | 22.5% |
| RandomForest | v1 | Direction (UP vs DOWN closing move) | 60.8% | 62.5% | 61.4% | 52.0% |
| RandomForest | **v2 (+ cross-asset)** | **Direction — used in production** | **62.0%** | **64.9%** | 58.5% | 52.0% |

Cross-asset features (Bank Nifty, USD/INR, Crude oil, Dow Jones, Global VIX —
all lagged 1 day, no lookahead) were added specifically to test whether more
predictive data could improve accuracy, since 60-minute intraday price history
is hard-capped at ~2 years by the data provider (see "Data expansion" below).
**Result: cross-asset data genuinely improved directional prediction** (now
used in production in `cas_live_signal.py`) but **did not improve big-move
detection** (v1 features remain in production for that task).

**What this means in practice:**
- **Big-move detector** (v1 features): When it flags "high risk," there's
  roughly a **38%** chance it's actually correct (vs 22.5% base rate) — a real
  edge (+70% relative improvement over random), but still wrong more often
  than right. Best used as a **risk/volatility warning** (e.g., widen
  stop-loss, reduce size) rather than a standalone entry trigger.
- **Directional model** (v2 features, incl. cross-asset): 62.0% accuracy with
  64.9% precision on BULLISH calls is a **modest but genuine edge** over a
  coin flip (52% baseline). This is NOT high enough to bet large size on a
  single signal — it should be combined with position sizing, stop-losses,
  and ideally aggregated across multiple days/trades to realize the
  statistical edge (edge only pays off over many trades, not any single one).

## Data expansion: adding cross-asset features (v2)

Since 60-minute intraday Nifty history is hard-capped at ~2 years (492 trading
days) by Yahoo Finance — matching our existing dataset exactly — simply
"getting more days" of data wasn't possible through this data source. Instead,
`build_dataset_v2.py` enriches each EXISTING day with more PREDICTIVE FEATURES
from correlated markets (all lagged 1 day, no lookahead):

- **Bank Nifty** daily % change — India's most-traded index, highly correlated
- **USD/INR** daily % change — FII flow proxy; currency weakness often precedes
  Nifty weakness
- **Crude oil (WTI)** daily % change — India is a major oil importer; oil
  spikes are a classic Nifty headwind
- **Dow Jones** overnight % change — global risk-on/risk-off cue feeding into
  next-day Indian sentiment
- **Global VIX (US)** level + % change — global risk appetite, complements
  India VIX

Run `python3 backend/build_dataset_v2.py` to regenerate `master_dataset_v2.csv`
and `python3 backend/cas_ml_model_v2.py` to re-run the v1-vs-v2 comparison
backtest. Feature importance analysis showed USD/INR and Bank Nifty changes
rank among the top-10 most important features for the directional model.

## Key drivers found (feature importance + correlation analysis)

1. **Today's intraday move so far** (`abs_main_move`, `main_move_pct`) — largest
   single predictor of closing-window volatility.
2. **Recent closing-window volatility regime** (`rolling5/10_abs_close_move`) —
   volatility clusters; recent big-move days predict more to come.
3. **India VIX level** — higher VIX = higher closing-window move risk.
4. **Yesterday's closing-window move & its lag-2** (`prev_close_move`,
   `prev_close_move2`) — closing moves show autocorrelation (added in v2,
   boosted directional accuracy from ~53% to 60.5%).
5. **Futures basis & basis_change** — a stretched/moving basis signals
   arbitrage unwind risk into the close.
6. **PCR & pcr_change** — extreme/shifting PCR (especially <0.8, call-heavy)
   correlates with bigger closing swings.
7. Day-of-week: contrary to expectation, **Thursday (weekly expiry) shows the
   LOWEST average closing move**, and Mon/Tue/Wed show the highest — consistent
   with the CAS mechanism successfully dampening expiry-day manipulation, while
   news-driven moves dominate on non-expiry days.

## Known limitations (be aware of these before trusting the signal blindly)

1. **Limited history**: yfinance only provides 60-minute intraday history for
   ~2 years (492 trading days). More history (via a paid data vendor or NSE's
   own historical bhavcopy for spot, which goes back further) would improve
   statistical robustness.
2. **Proxy for the true CAS window**: We use the last 60-minute candle as a
   proxy for the actual closing auction window (NSE's CAS window is a shorter,
   specific slice of the last ~30 min). A tick-level or 1-minute data feed
   would allow a more precise definition of "closing window."
3. **NSE API fragility**: The live option-chain endpoint (`option-chain-v3`)
   is NSE's internal API and has changed paths multiple times historically.
   If `nse_options.py` starts failing, check NSE's website devtools network
   tab for the current endpoint path.
4. **F&O data lag**: NSE's official F&O bhavcopy is only published EOD, so the
   live signal necessarily uses **yesterday's** F&O snapshot (as the trained
   model does — no lookahead bias), not intraday OI changes happening today.
   A live NSE option-chain call (which IS real-time) is used only for PCR/max
   pain/strike selection, not for the ML model's OI-based features.
5. **No guarantee of continued edge**: Market microstructure (like CAS) can
   itself change over time (regulatory tweaks, participant adaptation), so the
   historical edge found here may decay. Recommend periodically re-running
   `build_dataset.py` + `cas_ml_model.py` to refresh/re-validate the model.

## Recommended usage in practice

1. Run `cas_live_signal.py` in the afternoon (ideally ~14:30-14:45 IST, before
   the closing window).
2. Use `risk_level` to decide whether to even take a position:
   - **HIGH**: consider a small directional position sized for volatility, or
     stay out if you're risk-averse.
   - **LOW**: closing-window move is likely to be small; not much edge to
     trade on it specifically.
3. Use `directional_bias` + `suggested_strike` as your entry idea, but always
   set a stop-loss — the model is a probabilistic edge, not a certainty.
4. Track your own live trade outcomes and periodically compare against the
   model's stated backtested precision/accuracy to confirm it's still working
   as expected (a decay in real-world performance vs backtest is a signal to
   retrain/re-tune).