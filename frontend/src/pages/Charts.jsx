import React, { useState, useEffect } from 'react';
import {
  ComposedChart, LineChart, BarChart,
  Line, Bar, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Legend
} from 'recharts';
import { RefreshCw, Loader, Lightbulb, TrendingUp, TrendingDown, Minus } from 'lucide-react';

const API = 'http://localhost:8001';

const INTERVAL_MAP = { '1D': '1d', '1H': '1h', '15M': '15m' };
const PERIOD_MAP = { '1M': '1mo', '3M': '3mo', '6M': '6mo', '1Y': '1y' };

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload || !payload.length) return null;
  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded p-3 text-xs shadow-lg">
      <p className="text-[#00d4aa] font-mono mb-1">{label}</p>
      {payload.map((p, i) => (
        p.value != null && (
          <div key={i} className="flex justify-between gap-4">
            <span style={{ color: p.color }}>{p.name}:</span>
            <span className="font-mono text-[#e8eaf6]">
              {typeof p.value === 'number' ? p.value.toFixed(2) : p.value}
            </span>
          </div>
        )
      ))}
    </div>
  );
};

export default function Charts({ signalData, loading: signalLoading }) {
  const [timeframe, setTimeframe] = useState('1D');
  const [period, setPeriod] = useState('6M');
  const [chartData, setChartData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showBB, setShowBB] = useState(true);
  const [showEMA, setShowEMA] = useState(true);
  const [showSupertrend, setShowSupertrend] = useState(false);

  const fetchChartData = async () => {
    setLoading(true);
    setError(null);
    try {
      const interval = INTERVAL_MAP[timeframe] || '1d';
      const per = PERIOD_MAP[period] || '6mo';
      const res = await fetch(`${API}/api/chart-data?interval=${interval}&period=${per}`);
      const json = await res.json();
      if (json.error) throw new Error(json.error);
      setChartData(json.data || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchChartData();
  }, [timeframe, period]);

  // Compute price domain for Y axis
  const priceDomain = chartData.length > 0 ? (() => {
    const closes = chartData.map(d => d.close).filter(Boolean);
    const highs = chartData.map(d => d.high).filter(Boolean);
    const lows = chartData.map(d => d.low).filter(Boolean);
    const min = Math.min(...lows) * 0.998;
    const max = Math.max(...highs) * 1.002;
    return [Math.round(min), Math.round(max)];
  })() : ['auto', 'auto'];

  // Thin out data for display (max 120 points)
  const displayData = chartData.length > 120
    ? chartData.filter((_, i) => i % Math.ceil(chartData.length / 120) === 0 || i === chartData.length - 1)
    : chartData;

  const latestClose = chartData.length > 0 ? chartData[chartData.length - 1]?.close : null;

  if (signalLoading) {
    return (
      <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6 h-96 flex items-center justify-center text-[#546e7a]">
        <Loader className="w-6 h-6 animate-spin mr-2" /> Loading...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap gap-4 bg-[#0f1629] border border-[#1a2035] rounded-lg p-4 items-center">
        <div className="flex gap-2">
          {['1D', '1H', '15M'].map(tf => (
            <button key={tf} onClick={() => setTimeframe(tf)}
              className={`px-3 py-1 rounded text-sm transition ${timeframe === tf ? 'bg-[#00d4aa] text-[#0a0e1a] font-semibold' : 'bg-[#1a2035] text-[#546e7a] hover:text-[#e8eaf6]'}`}>
              {tf}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          {['1M', '3M', '6M', '1Y'].map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`px-3 py-1 rounded text-sm transition ${period === p ? 'bg-[#00d4aa] text-[#0a0e1a] font-semibold' : 'bg-[#1a2035] text-[#546e7a] hover:text-[#e8eaf6]'}`}>
              {p}
            </button>
          ))}
        </div>
        <div className="flex gap-3 ml-auto items-center text-xs text-[#546e7a]">
          <label className="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" checked={showBB} onChange={e => setShowBB(e.target.checked)} className="accent-[#00d4aa]" />
            Bollinger
          </label>
          <label className="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" checked={showEMA} onChange={e => setShowEMA(e.target.checked)} className="accent-[#00d4aa]" />
            EMAs
          </label>
          <label className="flex items-center gap-1 cursor-pointer">
            <input type="checkbox" checked={showSupertrend} onChange={e => setShowSupertrend(e.target.checked)} className="accent-[#00d4aa]" />
            Supertrend
          </label>
          <button onClick={fetchChartData} className="p-1.5 hover:bg-[#1a2035] rounded transition text-[#00d4aa]">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-[#ff4757]/10 border border-[#ff4757]/30 rounded p-3 text-sm text-[#ff4757]">
          ⚠️ {error}
        </div>
      )}

      {loading ? (
        <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg h-80 flex items-center justify-center text-[#546e7a]">
          <Loader className="w-6 h-6 animate-spin mr-2" /> Fetching chart data...
        </div>
      ) : (
        <>
          {/* Price Chart */}
          <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-[#e8eaf6]">
                NIFTY 50 — Price
                {latestClose && <span className="ml-2 text-[#00d4aa] font-mono">{latestClose.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</span>}
              </h3>
              <div className="flex gap-3 text-xs text-[#546e7a]">
                {showEMA && <>
                  <span style={{ color: '#00d4aa' }}>— EMA9</span>
                  <span style={{ color: '#ffa502' }}>— EMA21</span>
                  <span style={{ color: '#ff4757' }}>— EMA50</span>
                  <span style={{ color: '#7c83fd' }}>— EMA200</span>
                </>}
                {showBB && <span style={{ color: '#546e7a' }}>⋯ BB</span>}
              </div>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={displayData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1a2035" />
                <XAxis dataKey="date" tick={{ fill: '#546e7a', fontSize: 10 }}
                  tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                <YAxis domain={priceDomain} tick={{ fill: '#546e7a', fontSize: 10 }}
                  tickFormatter={v => v?.toLocaleString('en-IN')} width={70} />
                <Tooltip content={<CustomTooltip />} />

                {/* Bollinger Bands */}
                {showBB && <>
                  <Line type="monotone" dataKey="bb_upper" stroke="#546e7a" strokeWidth={1}
                    dot={false} strokeDasharray="4 2" name="BB Upper" />
                  <Line type="monotone" dataKey="bb_mid" stroke="#546e7a" strokeWidth={1}
                    dot={false} strokeDasharray="2 2" name="BB Mid" />
                  <Line type="monotone" dataKey="bb_lower" stroke="#546e7a" strokeWidth={1}
                    dot={false} strokeDasharray="4 2" name="BB Lower" />
                </>}

                {/* EMAs */}
                {showEMA && <>
                  <Line type="monotone" dataKey="ema9" stroke="#00d4aa" strokeWidth={1.5}
                    dot={false} name="EMA9" />
                  <Line type="monotone" dataKey="ema21" stroke="#ffa502" strokeWidth={1.5}
                    dot={false} name="EMA21" />
                  <Line type="monotone" dataKey="ema50" stroke="#ff4757" strokeWidth={1.5}
                    dot={false} name="EMA50" />
                  <Line type="monotone" dataKey="ema200" stroke="#7c83fd" strokeWidth={2}
                    dot={false} name="EMA200" />
                </>}

                {/* Supertrend */}
                {showSupertrend && (
                  <Line type="monotone" dataKey="supertrend" stroke="#ffa502" strokeWidth={2}
                    dot={false} name="Supertrend" strokeDasharray="6 2" />
                )}

                {/* Close price */}
                <Line type="monotone" dataKey="close" stroke="#e8eaf6" strokeWidth={2}
                  dot={false} name="Close" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          {/* RSI + Stoch RSI */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4">
              <h3 className="text-sm font-semibold text-[#e8eaf6] mb-3">RSI (14)</h3>
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={displayData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a2035" />
                  <XAxis dataKey="date" tick={{ fill: '#546e7a', fontSize: 9 }}
                    tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                  <YAxis domain={[0, 100]} tick={{ fill: '#546e7a', fontSize: 10 }} width={30} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={70} stroke="#ff4757" strokeDasharray="4 2" strokeOpacity={0.6} />
                  <ReferenceLine y={30} stroke="#00d4aa" strokeDasharray="4 2" strokeOpacity={0.6} />
                  <ReferenceLine y={50} stroke="#546e7a" strokeDasharray="2 2" strokeOpacity={0.4} />
                  <Line type="monotone" dataKey="rsi" stroke="#ffa502" strokeWidth={2}
                    dot={false} name="RSI" />
                </ComposedChart>
              </ResponsiveContainer>
              <div className="flex gap-4 mt-1 text-xs text-[#546e7a]">
                <span className="text-[#ff4757]">— 70 Overbought</span>
                <span className="text-[#00d4aa]">— 30 Oversold</span>
              </div>
            </div>

            <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4">
              <h3 className="text-sm font-semibold text-[#e8eaf6] mb-3">Stochastic RSI</h3>
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={displayData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a2035" />
                  <XAxis dataKey="date" tick={{ fill: '#546e7a', fontSize: 9 }}
                    tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                  <YAxis domain={[0, 100]} tick={{ fill: '#546e7a', fontSize: 10 }} width={30} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={80} stroke="#ff4757" strokeDasharray="4 2" strokeOpacity={0.6} />
                  <ReferenceLine y={20} stroke="#00d4aa" strokeDasharray="4 2" strokeOpacity={0.6} />
                  <Line type="monotone" dataKey="stoch_k" stroke="#00d4aa" strokeWidth={1.5}
                    dot={false} name="%K" />
                  <Line type="monotone" dataKey="stoch_d" stroke="#ffa502" strokeWidth={1.5}
                    dot={false} name="%D" strokeDasharray="4 2" />
                </ComposedChart>
              </ResponsiveContainer>
              <div className="flex gap-4 mt-1 text-xs text-[#546e7a]">
                <span className="text-[#00d4aa]">— %K</span>
                <span className="text-[#ffa502]">— %D</span>
              </div>
            </div>
          </div>

          {/* MACD */}
          <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4">
            <h3 className="text-sm font-semibold text-[#e8eaf6] mb-3">MACD (12, 26, 9)</h3>
            <ResponsiveContainer width="100%" height={180}>
              <ComposedChart data={displayData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1a2035" />
                <XAxis dataKey="date" tick={{ fill: '#546e7a', fontSize: 9 }}
                  tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                <YAxis tick={{ fill: '#546e7a', fontSize: 10 }} width={60}
                  tickFormatter={v => v?.toFixed(0)} />
                <Tooltip content={<CustomTooltip />} />
                <ReferenceLine y={0} stroke="#546e7a" strokeOpacity={0.5} />
                <Bar dataKey="macd_hist" name="Histogram"
                  fill="#00d4aa"
                  label={false}
                  // Color bars based on value
                  isAnimationActive={false}
                />
                <Line type="monotone" dataKey="macd" stroke="#00d4aa" strokeWidth={1.5}
                  dot={false} name="MACD" />
                <Line type="monotone" dataKey="macd_signal" stroke="#ff4757" strokeWidth={1.5}
                  dot={false} name="Signal" strokeDasharray="4 2" />
              </ComposedChart>
            </ResponsiveContainer>
            <div className="flex gap-4 mt-1 text-xs text-[#546e7a]">
              <span className="text-[#00d4aa]">— MACD</span>
              <span className="text-[#ff4757]">— Signal</span>
              <span className="text-[#546e7a]">▌ Histogram</span>
            </div>
          </div>

          {/* ADX + Volume */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4">
              <h3 className="text-sm font-semibold text-[#e8eaf6] mb-3">ADX — Trend Strength</h3>
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={displayData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a2035" />
                  <XAxis dataKey="date" tick={{ fill: '#546e7a', fontSize: 9 }}
                    tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                  <YAxis domain={[0, 100]} tick={{ fill: '#546e7a', fontSize: 10 }} width={30} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={25} stroke="#ffa502" strokeDasharray="4 2" strokeOpacity={0.7} label={{ value: '25', fill: '#ffa502', fontSize: 9 }} />
                  <Line type="monotone" dataKey="adx" stroke="#7c83fd" strokeWidth={2}
                    dot={false} name="ADX" />
                </ComposedChart>
              </ResponsiveContainer>
              <p className="text-xs text-[#546e7a] mt-1">ADX &gt; 25 = strong trend</p>
            </div>

            <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4">
              <h3 className="text-sm font-semibold text-[#e8eaf6] mb-3">Volume Ratio (vs 14-day avg)</h3>
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={displayData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a2035" />
                  <XAxis dataKey="date" tick={{ fill: '#546e7a', fontSize: 9 }}
                    tickFormatter={v => v?.slice(5)} interval="preserveStartEnd" />
                  <YAxis tick={{ fill: '#546e7a', fontSize: 10 }} width={35}
                    tickFormatter={v => `${v?.toFixed(1)}x`} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={1} stroke="#546e7a" strokeOpacity={0.5} />
                  <ReferenceLine y={1.5} stroke="#ffa502" strokeDasharray="4 2" strokeOpacity={0.6} />
                  <Bar dataKey="volume_ratio" name="Vol Ratio" fill="#00d4aa" opacity={0.7} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
              <p className="text-xs text-[#546e7a] mt-1">&gt; 1.5x = high volume surge</p>
            </div>
          </div>

          {/* Current indicator snapshot — raw values, quick reference */}
          {signalData?.indicators && (
            <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4">
              <h3 className="text-sm font-semibold text-[#e8eaf6] mb-3">Current Indicator Snapshot</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: 'RSI (14)', value: signalData.indicators.rsi?.value?.toFixed(1), color: signalData.indicators.rsi?.bull > signalData.indicators.rsi?.bear ? '#00d4aa' : '#ff4757' },
                  { label: 'MACD', value: signalData.indicators.macd?.value?.toFixed(0), color: signalData.indicators.macd?.bull > signalData.indicators.macd?.bear ? '#00d4aa' : '#ff4757' },
                  { label: 'ADX', value: signalData.indicators.adx?.value?.toFixed(1), color: '#7c83fd' },
                  { label: 'ATR', value: signalData.indicators.atr?.value?.toFixed(0), color: '#ffa502' },
                  { label: 'EMA9', value: signalData.indicators.ema?.ema9?.toFixed(0), color: '#00d4aa' },
                  { label: 'EMA21', value: signalData.indicators.ema?.ema21?.toFixed(0), color: '#ffa502' },
                  { label: 'EMA50', value: signalData.indicators.ema?.ema50?.toFixed(0), color: '#ff4757' },
                  { label: 'EMA200', value: signalData.indicators.ema?.ema200?.toFixed(0), color: '#7c83fd' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="bg-[#1a2035] rounded p-3">
                    <p className="text-xs text-[#546e7a] mb-1">{label}</p>
                    <p className="text-lg font-bold font-mono" style={{ color }}>{value ?? '—'}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Chart analysis synthesis — turns the raw indicator scorecard into
              a readable, prioritized narrative: overall verdict first, then
              WHY each active indicator agrees/disagrees, using the exact
              same weighted scores computed in signal_engine.py (not
              duplicated logic — this simply surfaces reasoning that already
              exists but wasn't shown anywhere on this page before). */}
          {signalData && <ChartAnalysisCard signalData={signalData} />}
        </>
      )}
    </div>
  );
}

// ── Chart Analysis synthesis ─────────────────────────────────────────────
// Turns signalData.indicators (already computed with bull/bear scores +
// human-readable labels in backend/signal_engine.py) into a prioritized,
// readable narrative rather than a flat grid of numbers. Indicators with
// zero weight in the live signal (see WEIGHTS in signal_engine.py) are
// shown separately as "informational only" so it's clear they don't
// currently drive the BUY CE/BUY PE decision.

const ACTIVE_WEIGHTED_KEYS = ['macd', 'supertrend', 'candle_pattern']; // weight > 0 in signal_engine.py
const INDICATOR_DISPLAY_NAMES = {
  rsi: 'RSI (Momentum)',
  macd: 'MACD',
  bollinger: 'Bollinger Bands',
  ema: 'EMA Stack',
  adx: 'ADX (Trend Strength)',
  supertrend: 'Supertrend',
  stoch_rsi: 'Stochastic RSI',
  volume: 'Volume',
  candle_pattern: 'Candle Pattern',
};

function IndicatorReasonRow({ name, ind, active }) {
  const bull = ind?.bull ?? 0;
  const bear = ind?.bear ?? 0;
  const isBull = bull > bear;
  const isBear = bear > bull;
  const color = isBull ? '#00d4aa' : isBear ? '#ff4757' : '#546e7a';
  const Icon = isBull ? TrendingUp : isBear ? TrendingDown : Minus;

  return (
    <div className={`flex items-start gap-2 py-1.5 ${!active ? 'opacity-50' : ''}`}>
      <Icon className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" style={{ color }} />
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-[#e8eaf6]">{name}</span>
          {!active && <span className="text-[9px] text-[#546e7a] bg-[#1a2035] px-1.5 py-0.5 rounded">informational only</span>}
        </div>
        <p className="text-[11px] text-[#8892a6] mt-0.5">{ind?.label ?? 'N/A'}</p>
      </div>
    </div>
  );
}

function ChartAnalysisCard({ signalData }) {
  const { indicators, signal, direction, confidence, bull_confidence, bear_confidence, agreed_indicators, vix, vix_warning_message } = signalData;
  if (!indicators) return null;

  const verdictColor = signal === 'BUY CE' ? '#00d4aa' : signal === 'BUY PE' ? '#ff4757' : '#ffa502';
  const verdictLabel = signal === 'BUY CE' ? 'BULLISH — BUY CE' : signal === 'BUY PE' ? 'BEARISH — BUY PE' : 'STAY OUT';

  const activeEntries = ACTIVE_WEIGHTED_KEYS
    .map(key => [key, indicators[key]])
    .filter(([, ind]) => ind);
  const infoEntries = Object.entries(indicators)
    .filter(([key]) => !ACTIVE_WEIGHTED_KEYS.includes(key) && key !== 'candle_pattern');

  return (
    <div className="bg-[#0f1629] border-2 border-[#00d4aa]/30 rounded-lg p-5">
      <h3 className="text-sm font-bold text-[#e8eaf6] mb-4 flex items-center gap-2">
        <Lightbulb className="w-4 h-4 text-[#00d4aa]" />
        Chart Analysis & Signal Reasoning
      </h3>

      {/* Overall verdict */}
      <div className="flex items-center justify-between flex-wrap gap-3 bg-[#0a0e1a] border border-[#1a2035] rounded p-4 mb-4">
        <div>
          <p className="text-[10px] text-[#546e7a] uppercase">Overall Verdict</p>
          <p className="text-2xl font-bold font-mono" style={{ color: verdictColor }}>{verdictLabel}</p>
        </div>
        <div className="flex gap-6 text-right">
          <div>
            <p className="text-[10px] text-[#546e7a] uppercase">Bull Confidence</p>
            <p className="text-lg font-mono font-bold text-[#00d4aa]">{bull_confidence?.toFixed(1)}%</p>
          </div>
          <div>
            <p className="text-[10px] text-[#546e7a] uppercase">Bear Confidence</p>
            <p className="text-lg font-mono font-bold text-[#ff4757]">{bear_confidence?.toFixed(1)}%</p>
          </div>
        </div>
      </div>

      {vix_warning_message && (
        <div className="bg-[#ffa502]/10 border border-[#ffa502]/30 rounded p-2.5 mb-4 text-xs text-[#ffa502]">
          ⚠️ {vix_warning_message}
        </div>
      )}

      {/* Indicators actually driving the signal */}
      <p className="text-[10px] font-bold text-[#00d4aa] uppercase tracking-wide mb-1">
        Indicators Driving This Signal
      </p>
      <div className="divide-y divide-[#1a2035] mb-4">
        {activeEntries.map(([key, ind]) => (
          <IndicatorReasonRow key={key} name={INDICATOR_DISPLAY_NAMES[key] || key} ind={ind} active={true} />
        ))}
      </div>

      {/* Informational-only indicators (zero weight in the live signal) */}
      <p className="text-[10px] font-bold text-[#546e7a] uppercase tracking-wide mb-1">
        Informational Only (not currently weighted in the signal)
      </p>
      <div className="divide-y divide-[#1a2035]">
        {infoEntries.map(([key, ind]) => (
          <IndicatorReasonRow key={key} name={INDICATOR_DISPLAY_NAMES[key] || key} ind={ind} active={false} />
        ))}
      </div>

      <p className="text-[10px] text-[#3a4356] mt-4 italic">
        Weights are empirically calibrated from a 1-year walk-forward backtest (see comments in
        backend/signal_engine.py) — RSI/EMA/ADX/Bollinger/Stoch/Volume are shown for transparency
        but currently carry zero weight because they didn't add predictive value on daily Nifty data.
        Not investment advice — cross-check with the CAS Signal tab and options chain analysis.
      </p>
    </div>
  );
}
