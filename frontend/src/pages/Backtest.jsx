import React, { useState } from 'react';
import { Play, Loader, TrendingUp, TrendingDown, Target, BarChart2, Award, RefreshCw, Database, Activity, Info } from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine
} from 'recharts';

const API_BASE = 'http://localhost:8001';
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function StatCard({ label, value, sub, color = '#00d4aa' }) {
  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4">
      <p className="text-xs text-[#546e7a] mb-1">{label}</p>
      <p className="text-2xl font-bold font-mono" style={{ color }}>{value}</p>
      {sub && <p className="text-xs text-[#546e7a] mt-1">{sub}</p>}
    </div>
  );
}

function MonthlyHeatmap({ data }) {
  if (!data || data.length === 0) return null;

  const years = [...new Set(data.map(d => d.year))].sort();

  const getColor = (totalReturn) => {
    if (totalReturn > 50) return '#00d4aa';
    if (totalReturn > 20) return '#00b894';
    if (totalReturn > 0) return '#55efc4';
    if (totalReturn > -20) return '#ff7675';
    return '#ff4757';
  };

  const getCell = (year, monthIdx) => {
    const monthName = MONTHS[monthIdx];
    const entry = data.find(d => d.year === year && d.month_name === monthName);
    return entry || null;
  };

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
      <h3 className="text-lg font-bold text-[#e8eaf6] mb-4 flex items-center gap-2">
        <BarChart2 className="w-5 h-5 text-[#00d4aa]" />
        Monthly Returns Heatmap
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="text-left py-1 pr-3 text-[#546e7a] w-12">Year</th>
              {MONTHS.map(m => (
                <th key={m} className="text-center py-1 px-1 text-[#546e7a] w-14">{m}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map(year => (
              <tr key={year}>
                <td className="py-1 pr-3 text-[#546e7a] font-mono">{year}</td>
                {MONTHS.map((_, idx) => {
                  const cell = getCell(year, idx);
                  return (
                    <td key={idx} className="py-1 px-1 text-center">
                      {cell ? (
                        <div
                          className="rounded px-1 py-1 font-mono text-[#0a0e1a] font-bold text-xs"
                          style={{ backgroundColor: getColor(cell.total_return) }}
                          title={`${cell.trades} trades, ${cell.win_rate}% win rate`}
                        >
                          {cell.total_return > 0 ? '+' : ''}{cell.total_return}%
                        </div>
                      ) : (
                        <div className="rounded px-1 py-1 bg-[#1a2035] text-[#546e7a]">—</div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-4 mt-3 text-xs text-[#546e7a]">
        <span>Color scale:</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ backgroundColor: '#00d4aa' }}></span> &gt;50%</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ backgroundColor: '#55efc4' }}></span> 0–50%</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ backgroundColor: '#ff7675' }}></span> 0 to -20%</span>
        <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ backgroundColor: '#ff4757' }}></span> &lt;-20%</span>
      </div>
    </div>
  );
}

function EquityCurve({ data }) {
  if (!data || data.length === 0) return null;

  const startEquity = data[0]?.equity || 100000;
  const endEquity = data[data.length - 1]?.equity || 100000;
  const isProfit = endEquity >= startEquity;

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
      <h3 className="text-lg font-bold text-[#e8eaf6] mb-4 flex items-center gap-2">
        <TrendingUp className="w-5 h-5 text-[#00d4aa]" />
        Equity Curve
        <span className="text-sm font-normal text-[#546e7a] ml-2">
          Starting ₹1,00,000 · Risk 2% per trade
        </span>
      </h3>
      <ResponsiveContainer width="100%" height={250}>
        <AreaChart data={data} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={isProfit ? '#00d4aa' : '#ff4757'} stopOpacity={0.3} />
              <stop offset="95%" stopColor={isProfit ? '#00d4aa' : '#ff4757'} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1a2035" />
          <XAxis
            dataKey="date"
            tick={{ fill: '#546e7a', fontSize: 10 }}
            tickFormatter={(v) => v.slice(0, 7)}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: '#546e7a', fontSize: 10 }}
            tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`}
          />
          <Tooltip
            contentStyle={{ backgroundColor: '#0f1629', border: '1px solid #1a2035', borderRadius: 8 }}
            labelStyle={{ color: '#546e7a', fontSize: 11 }}
            formatter={(v) => [`₹${v.toLocaleString('en-IN')}`, 'Equity']}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke={isProfit ? '#00d4aa' : '#ff4757'}
            strokeWidth={2}
            fill="url(#equityGrad)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// Current weights from signal_engine.py v3 — CANDLE required, all others disabled
// MAX_POSSIBLE_SCORE = 1.0 + 1.0 + 1.5 = 3.5  (threshold 60% → CANDLE required)
const INDICATOR_WEIGHTS = {
  RSI: 0.0, MACD: 1.0, BOLLINGER: 0.0, EMA: 0.0,
  ADX: 0.0, SUPERTREND: 1.0, STOCH_RSI: 0.0, VOLUME: 0.0, CANDLE: 1.5,
};

function IndicatorPerformanceTable({ data }) {
  if (!data || !data.indicators) return null;

  const { baseline_win_rate, total_trades, indicators } = data;

  const verdictStyle = (verdict) => {
    switch (verdict) {
      case 'STRONG POSITIVE': return 'bg-[#00d4aa]/15 text-[#00d4aa] border border-[#00d4aa]/30';
      case 'POSITIVE': return 'bg-[#55efc4]/10 text-[#55efc4] border border-[#55efc4]/20';
      case 'NEUTRAL': return 'bg-[#546e7a]/10 text-[#546e7a] border border-[#546e7a]/20';
      case 'NEGATIVE': return 'bg-[#ffa502]/10 text-[#ffa502] border border-[#ffa502]/20';
      case 'STRONG NEGATIVE': return 'bg-[#ff4757]/15 text-[#ff4757] border border-[#ff4757]/30';
      case 'NEVER FIRES': return 'bg-[#1a2035] text-[#546e7a] border border-[#1a2035]';
      default: return 'bg-[#1a2035] text-[#546e7a]';
    }
  };

  const barData = indicators
    .filter(ind => ind.win_rate !== null)
    .map(ind => ({
      name: ind.indicator,
      win_rate: ind.win_rate,
      baseline: baseline_win_rate,
    }));

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6 space-y-5">
      <div className="flex items-start justify-between flex-wrap gap-3">
        <h3 className="text-lg font-bold text-[#e8eaf6] flex items-center gap-2">
          <Activity className="w-5 h-5 text-[#00d4aa]" />
          Indicator Performance Analysis
        </h3>
        <div className="flex items-center gap-2 text-xs text-[#546e7a] bg-[#1a2035] px-3 py-1.5 rounded">
          <Info className="w-3.5 h-3.5 text-[#00d4aa]" />
          Baseline win rate: <span className="text-[#e8eaf6] font-mono font-bold ml-1">{baseline_win_rate}%</span>
          <span className="ml-2">({total_trades} trades)</span>
        </div>
      </div>

      {/* Win Rate Bar Chart */}
      <div>
        <p className="text-xs text-[#546e7a] mb-2">Win rate when indicator fires vs baseline ({baseline_win_rate}%)</p>
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={barData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a2035" vertical={false} />
            <XAxis dataKey="name" tick={{ fill: '#546e7a', fontSize: 10 }} />
            <YAxis tick={{ fill: '#546e7a', fontSize: 10 }} domain={[0, 100]} tickFormatter={v => `${v}%`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#0f1629', border: '1px solid #1a2035', borderRadius: 8 }}
              formatter={(v, name) => [`${v}%`, name === 'win_rate' ? 'Win Rate' : 'Baseline']}
              labelStyle={{ color: '#e8eaf6', fontSize: 11 }}
            />
            <ReferenceLine y={baseline_win_rate} stroke="#ffa502" strokeDasharray="4 4" strokeWidth={1.5} label={{ value: 'Baseline', fill: '#ffa502', fontSize: 9, position: 'right' }} />
            <Bar dataKey="win_rate" radius={[3, 3, 0, 0]}>
              {barData.map((entry, i) => (
                <Cell
                  key={i}
                  fill={entry.win_rate >= 60 ? '#00d4aa' : entry.win_rate >= baseline_win_rate ? '#55efc4' : entry.win_rate >= 30 ? '#ffa502' : '#ff4757'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Per-indicator table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1a2035]">
              <th className="text-left py-2 text-[#546e7a]">Indicator</th>
              <th className="text-right py-2 text-[#546e7a]">Fires</th>
              <th className="text-right py-2 text-[#546e7a]">W / L</th>
              <th className="text-right py-2 text-[#546e7a]">Win Rate</th>
              <th className="text-right py-2 text-[#546e7a]">vs Baseline</th>
              <th className="text-right py-2 text-[#546e7a]">Avg Return</th>
              <th className="text-right py-2 text-[#546e7a]">Weight</th>
              <th className="text-center py-2 text-[#546e7a]">Verdict</th>
            </tr>
          </thead>
          <tbody>
            {indicators.map((row, i) => (
              <tr key={i} className="border-b border-[#1a2035] hover:bg-[#1a2035] transition">
                <td className="py-2 text-[#e8eaf6] font-mono font-bold text-xs">{row.indicator}</td>
                <td className="py-2 text-right text-[#546e7a] text-xs">{row.fires}</td>
                <td className="py-2 text-right text-xs">
                  {row.fires > 0 ? (
                    <span>
                      <span className="text-[#00d4aa]">{row.wins}</span>
                      <span className="text-[#546e7a]">/</span>
                      <span className="text-[#ff4757]">{row.losses}</span>
                    </span>
                  ) : <span className="text-[#546e7a]">—</span>}
                </td>
                <td className={`py-2 text-right font-mono font-bold text-xs ${
                  row.win_rate === null ? 'text-[#546e7a]' :
                  row.win_rate >= 60 ? 'text-[#00d4aa]' :
                  row.win_rate >= baseline_win_rate ? 'text-[#55efc4]' :
                  row.win_rate >= 30 ? 'text-[#ffa502]' : 'text-[#ff4757]'
                }`}>
                  {row.win_rate !== null ? `${row.win_rate}%` : '—'}
                </td>
                <td className={`py-2 text-right font-mono text-xs ${
                  row.vs_baseline === null ? 'text-[#546e7a]' :
                  row.vs_baseline > 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]'
                }`}>
                  {row.vs_baseline !== null ? `${row.vs_baseline > 0 ? '+' : ''}${row.vs_baseline}%` : '—'}
                </td>
                <td className={`py-2 text-right font-mono text-xs ${
                  row.avg_return === null ? 'text-[#546e7a]' :
                  row.avg_return > 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]'
                }`}>
                  {row.avg_return !== null ? `${row.avg_return > 0 ? '+' : ''}${row.avg_return}%` : '—'}
                </td>
                <td className="py-2 text-right font-mono text-xs text-[#546e7a]">
                  {INDICATOR_WEIGHTS[row.indicator] !== undefined ? INDICATOR_WEIGHTS[row.indicator].toFixed(1) : '—'}
                </td>
                <td className="py-2 text-center">
                  <span className={`text-xs font-semibold px-2 py-0.5 rounded ${verdictStyle(row.verdict)}`}>
                    {row.verdict}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-[#546e7a] italic">
        * Weights shown are the current tuned values in the signal engine. Higher weight = more influence on confidence score.
        Indicators with NEGATIVE/STRONG NEGATIVE verdict have been down-weighted to reduce false signals.
      </p>
    </div>
  );
}

function IndicatorComboTable({ data }) {
  if (!data || data.length === 0) return null;

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
      <h3 className="text-lg font-bold text-[#e8eaf6] mb-4 flex items-center gap-2">
        <Award className="w-5 h-5 text-[#ffa502]" />
        Best Indicator Combinations
        <span className="text-xs font-normal text-[#546e7a] ml-1">(top 10 by win rate)</span>
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#1a2035]">
              <th className="text-left py-2 text-[#546e7a]">Indicators Agreed</th>
              <th className="text-right py-2 text-[#546e7a]">Trades</th>
              <th className="text-right py-2 text-[#546e7a]">W / L</th>
              <th className="text-right py-2 text-[#546e7a]">Win Rate</th>
              <th className="text-right py-2 text-[#546e7a]">Avg Return</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className="border-b border-[#1a2035] hover:bg-[#1a2035] transition">
                <td className="py-2 text-[#e8eaf6] text-xs font-mono">{row.combo}</td>
                <td className="py-2 text-right text-[#546e7a] text-xs">{row.total_trades}</td>
                <td className="py-2 text-right text-xs">
                  <span className="text-[#00d4aa]">{row.wins}</span>
                  <span className="text-[#546e7a]">/</span>
                  <span className="text-[#ff4757]">{row.losses}</span>
                </td>
                <td className={`py-2 text-right font-bold font-mono text-xs ${
                  row.win_rate >= 60 ? 'text-[#00d4aa]' : row.win_rate >= 50 ? 'text-[#ffa502]' : 'text-[#ff4757]'
                }`}>
                  {row.win_rate}%
                </td>
                <td className={`py-2 text-right font-mono text-xs ${
                  row.avg_return > 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]'
                }`}>
                  {row.avg_return > 0 ? '+' : ''}{row.avg_return}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function Backtest() {
  const [period, setPeriod] = useState('1y');
  const [threshold, setThreshold] = useState(60);
  const [signalType, setSignalType] = useState('both');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [showAllTrades, setShowAllTrades] = useState(false);

  const runBacktest = async (forceRefresh = false) => {
    setLoading(true);
    setResults(null);
    try {
      const url = `${API_BASE}/api/backtest?period=${period}&confidence_threshold=${threshold}&signal_type=${signalType}${forceRefresh ? '&force_refresh=true' : ''}`;
      const response = await fetch(url);
      const data = await response.json();
      setResults(data);
    } catch (error) {
      console.error('Backtest error:', error);
    } finally {
      setLoading(false);
    }
  };

  const s = results?.summary;
  const trades = results?.trades || [];
  const displayTrades = showAllTrades ? trades : trades.slice(0, 15);

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
        <h2 className="text-lg font-bold text-[#e8eaf6] mb-4">Backtest Configuration</h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="text-sm text-[#546e7a] mb-2 block">Period</label>
            <select
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-[#e8eaf6] text-sm"
            >
              <option value="6mo">6 Months</option>
              <option value="1y">1 Year</option>
              <option value="2y">2 Years</option>
            </select>
          </div>

          <div>
            <label className="text-sm text-[#546e7a] mb-2 block">
              Confidence Threshold: <span className="text-[#00d4aa] font-mono">{threshold}%</span>
            </label>
            <input
              type="range"
              min="40"
              max="90"
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full accent-[#00d4aa]"
            />
            <div className="flex justify-between text-xs text-[#546e7a] mt-1">
              <span>40% (more signals)</span>
              <span>90% (fewer, higher quality)</span>
            </div>
          </div>

          <div>
            <label className="text-sm text-[#546e7a] mb-2 block">Signal Type</label>
            <select
              value={signalType}
              onChange={(e) => setSignalType(e.target.value)}
              className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-[#e8eaf6] text-sm"
            >
              <option value="both">Both CE & PE</option>
              <option value="bullish">CE Only (Bullish)</option>
              <option value="bearish">PE Only (Bearish)</option>
            </select>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3 flex-wrap">
          <button
            onClick={() => runBacktest(false)}
            disabled={loading}
            className="bg-[#00d4aa] text-[#0a0e1a] px-6 py-2 rounded font-semibold flex items-center gap-2 hover:bg-[#00d4aa]/90 disabled:opacity-50 transition"
          >
            {loading ? (
              <>
                <Loader className="w-4 h-4 animate-spin" />
                Running backtest... (may take 30–60s)
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                Run Backtest
              </>
            )}
          </button>
          <button
            onClick={() => runBacktest(true)}
            disabled={loading}
            className="bg-[#1a2035] text-[#546e7a] px-4 py-2 rounded font-semibold flex items-center gap-2 hover:text-[#e8eaf6] hover:bg-[#1a2035]/80 disabled:opacity-50 transition text-sm"
            title="Bypass cache and re-run from scratch"
          >
            <RefreshCw className="w-4 h-4" />
            Force Refresh
          </button>
          {results?._cached && (
            <span className="flex items-center gap-1.5 text-xs text-[#546e7a] bg-[#1a2035] px-3 py-1.5 rounded">
              <Database className="w-3.5 h-3.5 text-[#00d4aa]" />
              Loaded from cache (today's run)
            </span>
          )}
        </div>
      </div>

      {/* Summary Stats */}
      {results && s && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard
              label="Win Rate"
              value={`${s.win_rate?.toFixed(1)}%`}
              sub={`${trades.filter(t => t.result === 'WIN').length}W / ${trades.filter(t => t.result === 'LOSS').length}L`}
              color={s.win_rate >= 55 ? '#00d4aa' : s.win_rate >= 45 ? '#ffa502' : '#ff4757'}
            />
            <StatCard
              label="Total Return"
              value={`${s.total_return_pct > 0 ? '+' : ''}${s.total_return_pct?.toFixed(1)}%`}
              sub="on ₹1,00,000 capital"
              color={s.total_return_pct >= 0 ? '#00d4aa' : '#ff4757'}
            />
            <StatCard
              label="Sharpe Ratio"
              value={s.sharpe_ratio?.toFixed(2)}
              sub={s.sharpe_ratio >= 1 ? 'Good risk-adjusted return' : 'Below benchmark'}
              color={s.sharpe_ratio >= 1 ? '#00d4aa' : s.sharpe_ratio >= 0 ? '#ffa502' : '#ff4757'}
            />
            <StatCard
              label="Max Drawdown"
              value={`-${s.max_drawdown_pct?.toFixed(1)}%`}
              sub="worst peak-to-trough"
              color={s.max_drawdown_pct <= 20 ? '#00d4aa' : s.max_drawdown_pct <= 40 ? '#ffa502' : '#ff4757'}
            />
            <StatCard
              label="Profit Factor"
              value={s.profit_factor?.toFixed(2)}
              sub="gross profit / gross loss"
              color={s.profit_factor >= 1.5 ? '#00d4aa' : s.profit_factor >= 1 ? '#ffa502' : '#ff4757'}
            />
            <StatCard
              label="Avg Return/Trade"
              value={`${s.avg_return_per_trade > 0 ? '+' : ''}${s.avg_return_per_trade?.toFixed(1)}%`}
              sub="option premium return"
              color={s.avg_return_per_trade >= 0 ? '#00d4aa' : '#ff4757'}
            />
            <StatCard
              label="Best Trade"
              value={`+${s.best_trade?.toFixed(1)}%`}
              color="#00d4aa"
            />
            <StatCard
              label="Worst Trade"
              value={`${s.worst_trade?.toFixed(1)}%`}
              sub={`Avg hold: ${s.avg_holding_days?.toFixed(1)} days`}
              color="#ff4757"
            />
          </div>

          {/* Signal breakdown */}
          <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4 flex gap-6 text-sm">
            <span className="text-[#546e7a]">Total Signals: <span className="text-[#e8eaf6] font-mono font-bold">{s.total_signals}</span></span>
            <span className="text-[#546e7a]">BUY CE: <span className="text-[#00d4aa] font-mono font-bold">{s.buy_ce_signals}</span></span>
            <span className="text-[#546e7a]">BUY PE: <span className="text-[#ff4757] font-mono font-bold">{s.buy_pe_signals}</span></span>
          </div>

          {/* Equity Curve */}
          <EquityCurve data={results.equity_curve} />

          {/* Monthly Heatmap */}
          <MonthlyHeatmap data={results.monthly_returns} />

          {/* Indicator Performance Analysis */}
          <IndicatorPerformanceTable data={results.indicator_performance} />

          {/* Indicator Combo Analysis */}
          <IndicatorComboTable data={results.win_by_indicator_combo} />

          {/* Trade Log */}
          <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
            <h3 className="text-lg font-bold text-[#e8eaf6] mb-4 flex items-center gap-2">
              <Target className="w-5 h-5 text-[#00d4aa]" />
              Trade Log
              <span className="text-sm font-normal text-[#546e7a]">({trades.length} total)</span>
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[#1a2035]">
                    <th className="text-left py-2 text-[#546e7a]">Date</th>
                    <th className="text-left py-2 text-[#546e7a]">Signal</th>
                    <th className="text-left py-2 text-[#546e7a]">Strike</th>
                    <th className="text-right py-2 text-[#546e7a]">Entry</th>
                    <th className="text-right py-2 text-[#546e7a]">Exit</th>
                    <th className="text-right py-2 text-[#546e7a]">Conf.</th>
                    <th className="text-right py-2 text-[#546e7a]">DTE</th>
                    <th className="text-right py-2 text-[#546e7a]">Days</th>
                    <th className="text-right py-2 text-[#546e7a]">Return</th>
                    <th className="text-center py-2 text-[#546e7a]">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {displayTrades.map((trade, i) => (
                    <tr key={i} className="border-b border-[#1a2035] hover:bg-[#1a2035] transition">
                      <td className="py-2 text-[#546e7a] text-xs">{trade.date}</td>
                      <td className={`py-2 font-mono font-bold text-xs ${
                        trade.signal === 'BUY CE' ? 'text-[#00d4aa]' : 'text-[#ff4757]'
                      }`}>{trade.signal}</td>
                      <td className="py-2 text-[#e8eaf6] font-mono text-xs">{trade.strike}</td>
                      <td className="py-2 text-right font-mono text-[#e8eaf6] text-xs">{trade.entry_spot?.toFixed(0)}</td>
                      <td className="py-2 text-right font-mono text-[#e8eaf6] text-xs">{trade.exit_spot?.toFixed(0)}</td>
                      <td className="py-2 text-right font-mono text-[#546e7a] text-xs">{trade.confidence?.toFixed(0)}%</td>
                      <td className="py-2 text-right font-mono text-xs" style={{ color: trade.dte <= 3 ? '#ffa502' : '#546e7a' }}
                          title="Days to expiry at entry">
                        {trade.dte ?? '—'}
                      </td>
                      <td className="py-2 text-right text-[#546e7a] text-xs">{trade.holding_days}d</td>
                      <td className={`py-2 text-right font-mono font-bold text-xs ${
                        trade.pct_return > 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]'
                      }`}>
                        {trade.pct_return > 0 ? '+' : ''}{trade.pct_return?.toFixed(1)}%
                      </td>
                      <td className="py-2 text-center">
                        <span className={`text-xs font-bold px-2 py-0.5 rounded ${
                          trade.result === 'WIN'
                            ? 'bg-[#00d4aa]/10 text-[#00d4aa]'
                            : 'bg-[#ff4757]/10 text-[#ff4757]'
                        }`}>
                          {trade.result}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {trades.length > 15 && (
              <button
                onClick={() => setShowAllTrades(!showAllTrades)}
                className="mt-4 text-sm text-[#00d4aa] hover:underline"
              >
                {showAllTrades ? 'Show less' : `Show all ${trades.length} trades`}
              </button>
            )}
          </div>
        </>
      )}

      {!results && !loading && (
        <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-12 text-center text-[#546e7a]">
          <BarChart2 className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p className="text-lg mb-1">No backtest results yet</p>
          <p className="text-sm">Configure parameters above and click "Run Backtest"</p>
          <p className="text-xs mt-2 text-[#546e7a]/60">Walk-forward simulation on historical Nifty data. May take 30–60 seconds.</p>
        </div>
      )}
    </div>
  );
}
