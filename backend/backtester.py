"""
Backtest engine - simulates historical signal performance
Includes real equity curve, monthly returns heatmap, and proper Sharpe ratio
"""
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from data import fetch_nifty, fetch_vix, fetch_vix_history
from indicators import compute_all_indicators
from signal_engine import generate_signal

logger = logging.getLogger(__name__)

# NSE changed Nifty weekly options expiry from Thursday to Tuesday
# First Tuesday expiry: September 18, 2025
EXPIRY_CHANGE_DATE = datetime(2025, 9, 18)
THURSDAY = 3  # weekday() index
TUESDAY = 1   # weekday() index


def get_expiry_weekday(trade_date):
    """Return the correct expiry weekday for a given trade date."""
    if trade_date >= EXPIRY_CHANGE_DATE:
        return TUESDAY
    return THURSDAY


def get_next_expiry(trade_date):
    """Get the next weekly expiry date on or after the given trade date."""
    expiry_weekday = get_expiry_weekday(trade_date)
    days_ahead = expiry_weekday - trade_date.weekday()
    if days_ahead <= 0:  # Already past (or on) this week's expiry day
        days_ahead += 7
    return trade_date + timedelta(days=days_ahead)


def get_dte(trade_date):
    """Return calendar days to the next weekly expiry from trade_date."""
    if isinstance(trade_date, pd.Timestamp):
        trade_date = trade_date.to_pydatetime()
    next_expiry = get_next_expiry(trade_date)
    dte = (next_expiry - trade_date).days
    return max(0, dte)


def estimate_option_return(entry_spot, exit_spot, signal_type, atr, vix=15.0):
    """
    Estimate option premium return based on spot movement.
    Uses VIX-adjusted premium estimation instead of fixed delta.
    """
    spot_move = abs(exit_spot - entry_spot)

    # Delta approximation: ATM ~0.5, OTM ~0.4
    delta = 0.45

    # Premium estimate: use VIX to scale (higher VIX = more expensive premiums)
    # Base premium = 1.5% of spot, scaled by VIX/15
    vix_multiplier = max(0.5, vix / 15.0)
    premium_estimate = entry_spot * 0.015 * vix_multiplier

    if signal_type == "BUY PE":
        direction = -1 if exit_spot < entry_spot else 1
    else:  # BUY CE
        direction = 1 if exit_spot > entry_spot else -1

    pnl = direction * spot_move * delta

    if premium_estimate < 1:
        return 0.0

    return_pct = (pnl / premium_estimate) * 100
    # Cap returns to realistic range: -100% to +300%
    return float(np.clip(return_pct, -100, 300))


def simulate_trade(df, entry_idx, signal_type, entry_spot, atr, max_hold_days=5):
    """
    Simulate a trade from entry to exit.
    Exit conditions:
    - Target hit (2.5x ATR)
    - Stop-loss hit (1.5x ATR)
    - Max hold days elapsed
    """
    if signal_type == "BUY CE":
        sl = entry_spot - 1.5 * atr
        tgt = entry_spot + 2.5 * atr
    else:  # BUY PE
        sl = entry_spot + 1.5 * atr
        tgt = entry_spot - 2.5 * atr

    holding_days = 0

    for j in range(1, max_hold_days + 1):
        if entry_idx + j >= len(df):
            break

        candle = df.iloc[entry_idx + j]
        holding_days = j

        if signal_type == "BUY CE":
            if candle["High"] >= tgt:
                return tgt, "WIN", j
            if candle["Low"] <= sl:
                return sl, "LOSS", j
        else:  # BUY PE
            if candle["Low"] <= tgt:
                return tgt, "WIN", j
            if candle["High"] >= sl:
                return sl, "LOSS", j

    # Exit at last candle close if no exit condition met
    exit_idx = entry_idx + min(holding_days, max_hold_days)
    exit_spot = df.iloc[exit_idx]["Close"]

    if signal_type == "BUY CE":
        result = "WIN" if exit_spot > entry_spot else "LOSS"
    else:
        result = "WIN" if exit_spot < entry_spot else "LOSS"

    return exit_spot, result, holding_days


def calculate_sharpe_ratio(returns, risk_free_rate=0.065):
    """
    Calculate annualized Sharpe ratio from a list of trade returns.
    risk_free_rate: Indian risk-free rate (~6.5% for 2024)
    """
    if len(returns) < 2:
        return 0.0

    returns_arr = np.array(returns)
    mean_return = np.mean(returns_arr)
    std_return = np.std(returns_arr, ddof=1)

    if std_return == 0:
        return 0.0

    # Annualize: assume ~52 trades per year (weekly options)
    trades_per_year = 52
    daily_rf = risk_free_rate / trades_per_year

    sharpe = (mean_return - daily_rf) / std_return * np.sqrt(trades_per_year)
    return float(round(sharpe, 2))


def calculate_max_drawdown(equity_curve):
    """Calculate maximum drawdown from equity curve"""
    if len(equity_curve) < 2:
        return 0.0

    equity_arr = np.array(equity_curve)
    peak = np.maximum.accumulate(equity_arr)
    drawdown = (equity_arr - peak) / peak * 100
    return float(abs(drawdown.min()))


def run_backtest(period="1y", interval="1d", confidence_threshold=65.0, signal_type="both"):
    """
    Run walk-forward backtest of the signal engine.

    For each historical candle, generate a signal on past-only data and simulate a trade.
    Returns complete equity curve, monthly returns heatmap, and real statistics.
    """
    logger.info(f"Starting backtest: period={period}, confidence_threshold={confidence_threshold}")

    try:
        # Fetch data
        df = fetch_nifty(period, interval)

        if len(df) < 50:
            return {"error": "Insufficient data for backtest", "trades": []}

        # Compute indicators on full dataset
        df = compute_all_indicators(df)

        # Fetch historical VIX data for the same period
        try:
            vix_history = fetch_vix_history(period)
        except Exception:
            vix_history = None

        trades = []
        equity = 100000.0  # Starting capital ₹1,00,000
        equity_curve = [{"date": df.index[0].strftime("%Y-%m-%d"), "equity": equity}]
        peak = equity

        lookback = 50  # Minimum candles needed for indicators

        for i in range(lookback, len(df) - 5):
            # Create window with only past data (walk-forward)
            window = df.iloc[:i]

            # Get VIX for this date (use historical VIX if available, else 15.0)
            current_date = df.index[i]
            vix_for_date = 15.0
            if vix_history is not None and not vix_history.empty:
                try:
                    # Find closest VIX date on or before current date
                    vix_dates = vix_history.index[vix_history.index <= current_date]
                    if len(vix_dates) > 0:
                        vix_for_date = float(vix_history.loc[vix_dates[-1]])
                        if pd.isna(vix_for_date):
                            vix_for_date = 15.0
                except Exception:
                    vix_for_date = 15.0

            # Generate signal on window with real VIX
            signal_result = generate_signal(window, vix_for_date, confidence_threshold)

            # Filter by signal type if specified
            if signal_type == "bullish" and signal_result["signal"] != "BUY CE":
                continue
            if signal_type == "bearish" and signal_result["signal"] != "BUY PE":
                continue

            if signal_result["signal"] != "STAY OUT":
                entry_spot = df.iloc[i]["Close"]
                entry_date = df.index[i]
                atr = df.iloc[i]["ATR"]

                if pd.isna(atr) or atr <= 0:
                    continue

                # Day-of-week filter: skip Thursday and Friday entries
                # Thursday: DTE=0-1 (same-day expiry), theta destroys value
                # Friday: buying next week's options at peak weekend premium
                # Best days: Monday, Tuesday, Wednesday
                entry_weekday = entry_date.weekday() if isinstance(entry_date, datetime) else entry_date.to_pydatetime().weekday()
                if entry_weekday in (3, 4):  # 3=Thursday, 4=Friday
                    continue

                # Calculate days to expiry for this trade date
                dte = get_dte(entry_date)

                # Skip trades entered with < 2 days to expiry
                # (theta decay destroys option value too close to expiry)
                if dte < 2:
                    continue

                # Cap holding period at DTE so we never hold past expiry
                max_hold = min(dte, 5)

                # Simulate trade
                exit_spot, result, holding_days = simulate_trade(
                    df, i, signal_result["signal"], entry_spot, atr, max_hold_days=max_hold
                )

                # Calculate return using VIX-adjusted premium
                pct_return = estimate_option_return(
                    entry_spot, exit_spot, signal_result["signal"], atr
                )

                # Update equity (risk 2% of capital per trade)
                risk_amount = equity * 0.02
                if result == "WIN":
                    equity += risk_amount * (pct_return / 100)
                else:
                    equity -= risk_amount * (abs(pct_return) / 100)

                equity = max(equity, 0)  # Can't go below 0
                peak = max(peak, equity)

                exit_date = df.index[min(i + holding_days, len(df) - 1)]
                equity_curve.append({
                    "date": exit_date.strftime("%Y-%m-%d"),
                    "equity": round(equity, 2)
                })

                trades.append({
                    "date": entry_date.strftime("%Y-%m-%d"),
                    "signal": signal_result["signal"],
                    "confidence": float(signal_result["confidence"]),
                    "entry_spot": float(entry_spot),
                    "strike": f"{int(round(entry_spot / 100) * 100)} {'PE' if signal_result['direction'] == 'BEARISH' else 'CE'}",
                    "exit_spot": float(exit_spot),
                    "result": result,
                    "pct_return": float(pct_return),
                    "holding_days": holding_days,
                    "dte": dte,
                    "indicators_agreed": signal_result.get("agreed_indicators", [])
                })

        if not trades:
            return {
                "summary": {
                    "total_signals": 0,
                    "buy_ce_signals": 0,
                    "buy_pe_signals": 0,
                    "stay_out_signals": 0,
                    "win_rate": 0,
                    "avg_return_per_trade": 0,
                    "best_trade": 0,
                    "worst_trade": 0,
                    "total_return_pct": 0,
                    "max_drawdown_pct": 0,
                    "sharpe_ratio": 0,
                    "profit_factor": 0,
                    "avg_holding_days": 0,
                },
                "trades": [],
                "equity_curve": equity_curve,
                "monthly_returns": [],
                "win_by_indicator_combo": [],
            }

        # Calculate summary stats
        wins = [t for t in trades if t["result"] == "WIN"]
        losses = [t for t in trades if t["result"] == "LOSS"]
        all_returns = [t["pct_return"] for t in trades]

        win_rate = (len(wins) / len(trades) * 100) if trades else 0
        avg_win = np.mean([t["pct_return"] for t in wins]) if wins else 0
        avg_loss = np.mean([t["pct_return"] for t in losses]) if losses else 0
        total_return = (equity - 100000) / 100000 * 100

        buy_ce = len([t for t in trades if t["signal"] == "BUY CE"])
        buy_pe = len([t for t in trades if t["signal"] == "BUY PE"])

        gross_profit = sum(t["pct_return"] for t in wins) if wins else 0
        gross_loss = abs(sum(t["pct_return"] for t in losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 1.0

        sharpe = calculate_sharpe_ratio(all_returns)
        max_dd = calculate_max_drawdown([e["equity"] for e in equity_curve])

        # Build monthly returns heatmap
        monthly_returns = _build_monthly_returns(trades)

        # Build indicator combo win analysis
        win_by_indicator_combo = _build_indicator_combo_analysis(trades)

        # Build per-indicator performance analysis
        indicator_performance = _build_indicator_performance_analysis(trades)

        return {
            "summary": {
                "total_signals": len(trades),
                "buy_ce_signals": buy_ce,
                "buy_pe_signals": buy_pe,
                "stay_out_signals": 0,
                "win_rate": float(round(win_rate, 1)),
                "avg_return_per_trade": float(round(np.mean(all_returns), 1)),
                "best_trade": float(round(max(all_returns), 1)),
                "worst_trade": float(round(min(all_returns), 1)),
                "total_return_pct": float(round(total_return, 1)),
                "max_drawdown_pct": float(round(max_dd, 1)),
                "sharpe_ratio": sharpe,
                "profit_factor": float(round(profit_factor, 2)),
                "avg_holding_days": float(round(np.mean([t["holding_days"] for t in trades]), 1)),
            },
            "trades": trades,
            "equity_curve": equity_curve,
            "monthly_returns": monthly_returns,
            "win_by_indicator_combo": win_by_indicator_combo,
            "indicator_performance": indicator_performance,
        }

    except Exception as e:
        logger.error(f"Backtest error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "error": str(e),
            "summary": {},
            "trades": [],
            "equity_curve": [],
            "monthly_returns": [],
            "win_by_indicator_combo": [],
        }


def _build_monthly_returns(trades):
    """Build monthly returns data for heatmap"""
    if not trades:
        return []

    monthly = {}
    for trade in trades:
        date = datetime.strptime(trade["date"], "%Y-%m-%d")
        key = (date.year, date.month)
        if key not in monthly:
            monthly[key] = {"wins": 0, "losses": 0, "total_return": 0.0, "trades": 0}
        monthly[key]["trades"] += 1
        monthly[key]["total_return"] += trade["pct_return"]
        if trade["result"] == "WIN":
            monthly[key]["wins"] += 1
        else:
            monthly[key]["losses"] += 1

    result = []
    for (year, month), data in sorted(monthly.items()):
        win_rate = (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0
        result.append({
            "year": year,
            "month": month,
            "month_name": datetime(year, month, 1).strftime("%b"),
            "trades": data["trades"],
            "wins": data["wins"],
            "losses": data["losses"],
            "win_rate": round(win_rate, 1),
            "total_return": round(data["total_return"], 1),
        })

    return result


def _build_indicator_combo_analysis(trades):
    """Analyze which indicator combinations have the best win rates"""
    if not trades:
        return []

    combo_stats = {}
    for trade in trades:
        indicators = tuple(sorted(trade.get("indicators_agreed", [])))
        if not indicators:
            continue

        key = ", ".join(indicators)
        if key not in combo_stats:
            combo_stats[key] = {"wins": 0, "losses": 0, "total_return": 0.0}

        combo_stats[key]["total_return"] += trade["pct_return"]
        if trade["result"] == "WIN":
            combo_stats[key]["wins"] += 1
        else:
            combo_stats[key]["losses"] += 1

    result = []
    for combo, stats in combo_stats.items():
        total = stats["wins"] + stats["losses"]
        win_rate = (stats["wins"] / total * 100) if total > 0 else 0
        result.append({
            "combo": combo,
            "total_trades": total,
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": round(win_rate, 1),
            "avg_return": round(stats["total_return"] / total, 1) if total > 0 else 0,
        })

    # Sort by win rate descending
    result.sort(key=lambda x: x["win_rate"], reverse=True)
    return result[:10]  # Top 10 combos


def _build_indicator_performance_analysis(trades):
    """
    Per-indicator performance analysis:
    For each indicator, compute win rate and avg return when that indicator fires.
    Also computes baseline (all trades) for comparison.
    """
    if not trades:
        return []

    total_trades = len(trades)
    total_wins = sum(1 for t in trades if t["result"] == "WIN")
    baseline_win_rate = round((total_wins / total_trades * 100) if total_trades > 0 else 0, 1)

    # All known indicators that can appear in indicators_agreed
    all_indicators = ["MACD", "SUPERTREND", "EMA", "ADX", "RSI", "CANDLE", "BOLLINGER", "STOCH_RSI", "VOLUME"]

    result = []
    for ind in all_indicators:
        ind_trades = [t for t in trades if ind in t.get("indicators_agreed", [])]
        if not ind_trades:
            # Indicator never fired
            result.append({
                "indicator": ind,
                "fires": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": None,
                "avg_return": None,
                "vs_baseline": None,
                "verdict": "NEVER FIRES",
            })
            continue

        wins = [t for t in ind_trades if t["result"] == "WIN"]
        losses = [t for t in ind_trades if t["result"] == "LOSS"]
        win_rate = round(len(wins) / len(ind_trades) * 100, 1)
        avg_return = round(sum(t["pct_return"] for t in ind_trades) / len(ind_trades), 1)
        vs_baseline = round(win_rate - baseline_win_rate, 1)

        if win_rate >= 60:
            verdict = "STRONG POSITIVE"
        elif win_rate >= baseline_win_rate + 5:
            verdict = "POSITIVE"
        elif win_rate >= baseline_win_rate - 5:
            verdict = "NEUTRAL"
        elif win_rate >= 30:
            verdict = "NEGATIVE"
        else:
            verdict = "STRONG NEGATIVE"

        result.append({
            "indicator": ind,
            "fires": len(ind_trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "avg_return": avg_return,
            "vs_baseline": vs_baseline,
            "verdict": verdict,
        })

    # Sort: never-fires last, then by win_rate descending
    result.sort(key=lambda x: (x["win_rate"] is None, -(x["win_rate"] or 0)))

    return {
        "baseline_win_rate": baseline_win_rate,
        "total_trades": total_trades,
        "indicators": result,
    }
