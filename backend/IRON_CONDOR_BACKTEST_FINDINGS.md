# Iron Condor Historical Backtest — Findings & Recommendations

**Methodology**: Real 2-year historical data (Aug 2024 – Aug 2026, 492 trading
days, 104 actual weekly NIFTY expiry cycles) from `master_dataset_v2.csv`.
For every possible entry day (Fri/Mon/Tue/Wed) × OTM strike distance × wing
width, computed:
1. **Win rate** — did spot ever breach the short strike (using day HIGH/LOW,
   not just close) between entry and expiry?
2. **Actual P&L** — priced all 4 legs with Black-Scholes (using live VIX as
   the IV proxy) at entry, then settled at the real historical expiry-day
   close price. This matters because win rate alone is misleading for a
   premium-selling strategy — a 95% win rate can still lose money if the 5%
   losses are large enough.
3. **Year-by-year robustness** (2024 / 2025 / 2026 splits) to rule out
   overfitting to a single period.

All analysis scripts are in `backend/analyze_ic_*.py` — re-runnable anytime
against updated data via `python3 backend/analyze_ic_pnl_backtest.py`.

---

## Key Finding #1: Entry day (= days-to-expiry) is the dominant variable

| Entry Day | Avg DTE | Win rate @ 2.0% OTM | Win rate @ 2.5% OTM |
|---|---|---|---|
| **Tuesday** | 2.0 | 90.4% | **100.0%** |
| **Monday**  | 2.0 | 87.4% | 95.8% |
| Wednesday | 3.6 | 83.0% | 89.4% |
| Friday | 4.9 | 76.0% | 87.5% |

**Why**: less time-to-expiry = less time for spot to travel far enough to
breach a strike. Friday entries hold the position through the ENTIRE next
week (Mon–Thu), giving 4-5 full trading days of opportunity for a big move.
Tuesday/Monday entries only have 1-2 days remaining.

**This is a real, structural effect — not a fluke.** Verified year-by-year:
Tuesday @ 2.5% OTM was **100% win rate in both 2024 (n=18) and 2025 (n=34)**
independently.

## Key Finding #2: But Friday earns far more total premium (bigger position, wider range)

| Entry / Strategy | 2yr Total P&L (1 lot) | Avg P&L/trade | Win Rate | Worst Single Loss |
|---|---|---|---|---|
| **Friday, 1.5% OTM, 300pt wings** | ₹213,290 | ₹2,222 | 84.4% | -₹17,954 |
| **Friday, 2.0% OTM, 200pt wings** | ₹109,331 | ₹1,139 | 90.6% | -₹13,136 |
| **Monday, 2.5% OTM, 300pt wings** | ₹18,839 | ₹198 | 62.1% | -₹6,154 |
| **Tuesday, 2.5% OTM, 150pt wings** | ₹6,698 | ₹129 | **100.0%** | ₹0 (never lost!) |

**The tradeoff is explicit**: Friday entries collect much bigger premiums
(more time value = more IV to sell) but take on real tail risk (max drawdown
-₹17,954 in the worst historical week — Feb 2025's sharp selloff). Tuesday
entries collect small, safe premiums with **zero losing weeks in 2 years of
real data** — genuinely a free-money-shaped trade, just smaller.

## Key Finding #3: VIX-conditional entry meaningfully improves the risky Friday leg

Filtering Friday entries to only fire when **VIX ≤ 13** (skip ~57% of weeks
when VIX is elevated) raises win rate from 76.0% → **92.7%** at 2.0% OTM, and
87.5% → **97.6%** at 2.5% OTM. This is a genuine, actionable filter using
data already fetched live by this app (`vix` field, already in the CAS
signal pipeline).

## Key Finding #4: PCR did NOT show a strong directional skew signal

Tested whether Put-Call Ratio at entry predicts which side (call/put) is
more likely to breach — the relationship was weak and inconsistent across
entry days. **Not recommended as a filter.**

## Key Finding #5: The existing CAS "high-conviction" rule doesn't apply here

The app's validated high-conviction mean-reversion rule (86.5% win rate) is
a **rare, specific bullish-reversal pattern** that fired 0 times on Fridays
in this 2-year window — it's a different, much rarer signal (directional
bet, not a weekly income strategy) and not usable as an IC entry filter.

---

## RECOMMENDED STRATEGY (given you trade weekly NIFTY expiry)

**Primary approach — best risk-adjusted, matches your weekly trading cadence:**

> **Enter Tuesday (2 DTE), short strikes at 2.5% OTM, wings 150-200 points wide.**
> - 100% historical win rate across both full years of data tested
> - Zero losing weeks in the entire 2-year sample
> - Smaller premium (~₹130/lot/week average) but genuinely risk-free in
>   backtest — a strong "base" trade to run every single week

**Higher-premium complement — if you can tolerate real tail risk:**

> **Also enter Friday (4-5 DTE) when VIX ≤ 13-14, short strikes at 2.0-2.5%
> OTM, wings 200-300 points wide.**
> - Substantially higher average weekly premium (~₹1,100-2,200/lot)
> - 90-98% win rate when VIX-filtered (vs 76-87% unfiltered)
> - **BUT**: real max single-week loss of -₹13,000 to -₹18,000 per lot
>   occurred historically — this is NOT a "set and forget" trade; size it
>   according to your actual risk tolerance and consider adjusting/closing
>   early if spot approaches a short strike (the app's Live IC monitor
>   already alerts you to this)

**Running both together** (as separate positions) produced ₹116,029 combined
2-year total in the backtest (1 lot each), effectively diversifying between
a "safe weekly base" and a "higher-premium, VIX-timed" trade.

---

## Update: Dynamic OTM% scaling (fixes "suggestion too far away, negligible premium")

The static day-of-week recommendations above (e.g. "Monday → 2.5% OTM") were
calibrated on the **average DTE for that day across the 2-year backtest**
(~2 DTE for Monday). Applying that fixed 2.5% blindly on a day where the
ACTUAL DTE differs significantly — most extremely, on expiry day itself
(DTE=0) — massively overshoots the real expected move, since less time
remaining means a much smaller realistic price range. This produced
suggestions like short strikes 600+ points away when the real 1-sigma move
was only ~150 points, yielding near-zero premium (~₹1/share).

**Fix**: `iron_condor.get_recommended_params()` now accepts live `dte` and
`avg_iv_pct` and computes the OTM% DYNAMICALLY using the standard options
expected-move formula (`IV × sqrt(DTE/365)`), scaled by a per-day "sigma
multiplier" reverse-engineered from the backtest (e.g. Monday/Tuesday's
2.5%-OTM-at-~2-DTE historical result implies roughly a 2.4-sigma buffer —
that risk profile is preserved, but the ACTUAL point distance now correctly
adapts to today's real DTE/IV). Wing width scales down proportionally too.

Verified fix: on an actual DTE=0 expiry day with live IV≈14-19%, the static
2.5% OTM produced ₹1.25/share credit; the dynamic ~1.0% OTM (2.4σ) produces
₹12-14/share credit with a still-healthy ~79% probability of profit — a
~10x improvement in usable premium while keeping the validated risk profile.

`/api/iron-condor/recommendation` now fetches live DTE + ATM IV from the
NSE chain and passes them through, so the recommendation shown in the app
is always scaled to TODAY's actual conditions, not a stale fixed percentage.

## What changed in the app based on this analysis

- `backend/iron_condor.py` default `otm_distance_pct` and suggestion logic
  now reflect these backtested numbers (see code comments referencing this doc)
- New `/api/iron-condor/backtest-summary` endpoint exposes this analysis
  in-app so you can see the historical numbers before entering any trade
- Frontend Iron Condor page shows the backtested win rate / avg P&L for
  whatever entry-day + OTM% combination you're currently configuring

## Honest caveats

- **2 years of data, 104 weekly cycles** — a genuinely useful sample size,
  but still limited history; a true black-swan week (like a 2020-COVID-style
  10%+ single-day move) is NOT represented in this window and would breach
  even the widest strikes tested here.
- Premiums are **Black-Scholes-estimated using VIX as IV proxy**, not actual
  historical weekly-option order book data (which NSE doesn't provide
  cheaply/publicly for backtesting) — real fills will differ due to
  bid/ask spread, liquidity, and weekly-vs-30-day IV term structure
  differences. Treat the P&L numbers as directionally correct, not exact.
- Past performance never guarantees future results — this is standard
  options-selling risk (steady small wins, occasional sharp losses) and
  should be sized as a small % of capital, never all of it.