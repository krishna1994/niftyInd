import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  TrendingUp, TrendingDown, AlertTriangle, Target, Zap,
  RefreshCw, Clock, Info, ShieldAlert, Gauge, Activity,
  ArrowUpCircle, ArrowDownCircle, HelpCircle, Briefcase, AlertOctagon,
  LogOut, PauseCircle, DollarSign, Eye
} from 'lucide-react';

// Styling for the definitive recommendation badge on each position
const RECOMMENDATION_STYLES = {
  EXIT: { bg: 'bg-[#ff4757]/15', border: 'border-[#ff4757]/50', text: 'text-[#ff4757]', icon: LogOut, label: 'EXIT' },
  BOOK_PROFIT: { bg: 'bg-[#00d4aa]/15', border: 'border-[#00d4aa]/50', text: 'text-[#00d4aa]', icon: DollarSign, label: 'BOOK PROFIT' },
  MONITOR: { bg: 'bg-[#ffa502]/15', border: 'border-[#ffa502]/50', text: 'text-[#ffa502]', icon: Eye, label: 'MONITOR' },
  HOLD: { bg: 'bg-[#546e7a]/15', border: 'border-[#546e7a]/40', text: 'text-[#546e7a]', icon: PauseCircle, label: 'HOLD' },
};

const API_BASE = 'http://localhost:8001';
const REFRESH_MS = 20000; // poll every 20s (server itself caches for 15s)

// ── Small building blocks ───────────────────────────────────────────────────

function Pulse({ color }) {
  return (
    <span className="relative flex h-2.5 w-2.5">
      <span
        className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
        style={{ backgroundColor: color }}
      />
      <span
        className="relative inline-flex rounded-full h-2.5 w-2.5"
        style={{ backgroundColor: color }}
      />
    </span>
  );
}

function CircularGauge({ value, size = 120, stroke = 10, color, label, sublabel }) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(1, value ?? 0));
  const dashOffset = circumference * (1 - pct);

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke="#1a2035"
            strokeWidth={stroke}
            fill="none"
          />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            stroke={color}
            strokeWidth={stroke}
            fill="none"
            strokeLinecap="round"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: dashOffset }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold font-mono" style={{ color }}>
            {value != null ? `${Math.round(value * 100)}%` : '—'}
          </span>
        </div>
      </div>
      <p className="text-xs text-[#546e7a] mt-2 text-center">{label}</p>
      {sublabel && <p className="text-[10px] text-[#3a4356] text-center">{sublabel}</p>}
    </div>
  );
}

function RiskBadge({ level }) {
  const map = {
    HIGH: { bg: 'bg-[#ff4757]/15', text: 'text-[#ff4757]', ring: 'ring-[#ff4757]/30', label: 'HIGH RISK' },
    MEDIUM: { bg: 'bg-[#ffa502]/15', text: 'text-[#ffa502]', ring: 'ring-[#ffa502]/30', label: 'MEDIUM RISK' },
    LOW: { bg: 'bg-[#00d4aa]/15', text: 'text-[#00d4aa]', ring: 'ring-[#00d4aa]/30', label: 'LOW RISK' },
    UNKNOWN: { bg: 'bg-[#546e7a]/15', text: 'text-[#546e7a]', ring: 'ring-[#546e7a]/30', label: 'UNKNOWN' },
  };
  const c = map[level] || map.UNKNOWN;
  return (
    <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold ring-1 ${c.bg} ${c.text} ${c.ring}`}>
      <ShieldAlert className="w-3.5 h-3.5" />
      {c.label}
    </span>
  );
}

function BiasCard({ bias, confidence, pop, strike, action }) {
  const isBull = bias === 'BULLISH';
  const isBear = bias === 'BEARISH';
  const color = isBull ? '#00d4aa' : isBear ? '#ff4757' : '#546e7a';
  const Icon = isBull ? ArrowUpCircle : isBear ? ArrowDownCircle : HelpCircle;

  return (
    <motion.div
      layout
      className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-6 relative overflow-hidden"
    >
      <div
        className="absolute -top-10 -right-10 w-40 h-40 rounded-full opacity-10 blur-2xl"
        style={{ backgroundColor: color }}
      />
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs text-[#546e7a] uppercase tracking-wide font-semibold">Directional Bias</p>
        <Pulse color={color} />
      </div>

      <div className="flex items-center gap-3 mb-1">
        <Icon className="w-9 h-9" style={{ color }} />
        <motion.span
          key={bias}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-3xl font-extrabold"
          style={{ color }}
        >
          {bias || 'UNKNOWN'}
        </motion.span>
      </div>

      <div className="flex gap-6 mt-4">
        <div>
          <p className="text-[10px] text-[#546e7a] uppercase">Confidence</p>
          <p className="text-lg font-mono font-bold text-[#e8eaf6]">
            {confidence != null ? `${Math.round(confidence * 100)}%` : '—'}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-[#546e7a] uppercase flex items-center gap-1">
            POP <Info className="w-3 h-3" />
          </p>
          <p className="text-lg font-mono font-bold" style={{ color }}>
            {pop != null ? `${Math.round(pop * 100)}%` : '—'}
          </p>
        </div>
      </div>

      <div className="mt-5 pt-4 border-t border-[#1a2035] flex items-center justify-between">
        <div>
          <p className="text-[10px] text-[#546e7a] uppercase">Suggested Action</p>
          <p className="text-base font-bold" style={{ color }}>{action || '—'}</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-[#546e7a] uppercase">Strike</p>
          <p className="text-xl font-mono font-bold text-[#e8eaf6]">{strike ?? '—'}</p>
        </div>
      </div>
    </motion.div>
  );
}

function HighConvictionBanner({ detail }) {
  if (!detail) return null;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 200, damping: 20 }}
      className="relative bg-gradient-to-r from-[#00d4aa]/15 via-[#00d4aa]/5 to-transparent border border-[#00d4aa]/40 rounded-2xl p-5 overflow-hidden"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 bg-[#00d4aa]/20 rounded-xl">
          <Zap className="w-5 h-5 text-[#00d4aa]" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-bold text-[#00d4aa]">🎯 High-Conviction Pattern Detected</p>
          <p className="text-xs text-[#546e7a] mt-1">{detail.rule}</p>
          <div className="flex gap-4 mt-2 text-xs">
            <span className="text-[#e8eaf6]">
              Win rate: <span className="text-[#00d4aa] font-mono font-bold">{Math.round(detail.historical_win_rate * 100)}%</span>
              <span className="text-[#546e7a]"> (n={detail.historical_n})</span>
            </span>
            <span className="text-[#e8eaf6]">
              Direction: <span className="font-bold">{detail.direction}</span>
            </span>
          </div>
          <p className="text-[10px] text-[#546e7a] mt-2 italic">{detail.caveat}</p>
        </div>
      </div>
    </motion.div>
  );
}

function OIRow({ item }) {
  return (
    <div className="flex items-center justify-between py-1.5 text-xs">
      <span className="font-mono font-semibold text-[#e8eaf6]">{item.strike}</span>
      <span className="text-[#546e7a]">{(item.oi / 100000).toFixed(1)}L</span>
      <span style={{ color: item.oi_change >= 0 ? '#00d4aa' : '#ff4757' }}>
        {item.oi_change >= 0 ? '+' : ''}{(item.oi_change / 100000).toFixed(1)}L
      </span>
    </div>
  );
}

function ReasoningList({ items }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5">
      <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide mb-3 flex items-center gap-2">
        <Activity className="w-3.5 h-3.5" /> Model Reasoning
      </p>
      <ul className="space-y-1.5">
        {items.map((r, i) => (
          <motion.li
            key={i}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.04 }}
            className="text-xs text-[#8892a6] flex items-start gap-2"
          >
            <span className="text-[#00d4aa] mt-0.5">•</span>
            {r}
          </motion.li>
        ))}
      </ul>
    </div>
  );
}

// ── Skeleton loader ──────────────────────────────────────────────────────────

function SkeletonCard({ h = 'h-40' }) {
  return <div className={`${h} bg-[#0f1629] border border-[#1a2035] rounded-2xl animate-pulse`} />;
}

// ── Live Positions & Risk Alerts ─────────────────────────────────────────────
// Shows your ACTUAL live Zerodha positions (however they were opened) with
// live P&L and risk alerts cross-referenced against the current signal.
// Fully optional — silently shows nothing useful if Zerodha isn't connected
// (never shows a scary error for the common case of "not using this yet").

const ALERT_STYLES = {
  danger: { bg: 'bg-[#ff4757]/10', border: 'border-[#ff4757]/40', text: 'text-[#ff4757]' },
  warning: { bg: 'bg-[#ffa502]/10', border: 'border-[#ffa502]/40', text: 'text-[#ffa502]' },
  info: { bg: 'bg-[#00d4aa]/10', border: 'border-[#00d4aa]/40', text: 'text-[#00d4aa]' },
};

function LivePositionsCard() {
  const [data, setData] = useState(null);
  const [visible, setVisible] = useState(false);

  const fetchPositions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/positions/live`);
      const json = await res.json();
      setData(json);
      // Only show this card if there's actually something meaningful to show
      // (Zerodha connected AND at least one open position) — otherwise stay
      // invisible so users who haven't set up Zerodha never see it at all.
      setVisible(json.success && json.position_count > 0);
    } catch (e) {
      setVisible(false);
    }
  }, []);

  useEffect(() => {
    fetchPositions();
    const interval = setInterval(fetchPositions, 20000);
    return () => clearInterval(interval);
  }, [fetchPositions]);

  if (!visible || !data) return null;

  const totalPnl = data.positions.reduce((sum, p) => sum + p.pnl, 0);
  const totalAlerts = data.positions.reduce((sum, p) => sum + p.alerts.length, 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5"
    >
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide flex items-center gap-2">
          <Briefcase className="w-3.5 h-3.5" /> Live Positions
          <span className="text-[#e8eaf6] font-mono">({data.position_count})</span>
        </p>
        <div className="flex items-center gap-3">
          {totalAlerts > 0 && (
            <span className="inline-flex items-center gap-1 text-xs font-bold text-[#ffa502]">
              <AlertOctagon className="w-3.5 h-3.5" /> {totalAlerts} alert{totalAlerts !== 1 ? 's' : ''}
            </span>
          )}
          <span
            className="text-sm font-mono font-bold"
            style={{ color: totalPnl >= 0 ? '#00d4aa' : '#ff4757' }}
          >
            {totalPnl >= 0 ? '+' : ''}₹{totalPnl.toFixed(0)}
          </span>
        </div>
      </div>

      {data.iron_condor_exit_signal?.detected && (() => {
        const ic = data.iron_condor_exit_signal;
        const style = RECOMMENDATION_STYLES[ic.recommendation] || RECOMMENDATION_STYLES.HOLD;
        const Icon = style.icon;
        return (
          <div className={`mb-3 ${style.bg} border ${style.border} rounded-xl p-3`}>
            <div className="flex items-center justify-between flex-wrap gap-2 mb-1.5">
              <span className={`inline-flex items-center gap-1.5 text-xs font-bold px-2 py-1 rounded ${style.text}`}>
                <Icon className="w-3.5 h-3.5" /> IRON CONDOR: {style.label}
              </span>
              <span className="text-xs text-[#546e7a]">
                Spot {ic.spot_price} · Short Call {ic.short_call_strike} · Short Put {ic.short_put_strike}
              </span>
            </div>
            {ic.reasons?.map((r, j) => (
              <p key={j} className={`text-[11px] ${style.text} mt-1`}>{r.message}</p>
            ))}
          </div>
        );
      })()}

      <div className="space-y-3">
        {data.positions.map((pos, i) => {
          const recStyle = RECOMMENDATION_STYLES[pos.recommendation] || RECOMMENDATION_STYLES.HOLD;
          const RecIcon = recStyle.icon;
          return (
            <div key={i} className="bg-[#0a0e1a] border border-[#1a2035] rounded-xl p-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-bold px-2 py-0.5 rounded ${
                      pos.option_type === 'CE' ? 'bg-[#00d4aa]/15 text-[#00d4aa]' : 'bg-[#ff4757]/15 text-[#ff4757]'
                    }`}
                  >
                    {pos.option_type || '—'}{pos.strike ? ` ${pos.strike}` : ''}
                  </span>
                  <span className="text-sm font-mono text-[#e8eaf6]">{pos.tradingsymbol}</span>
                  <span className="text-xs text-[#546e7a]">× {pos.quantity}</span>
                  <span
                    className={`inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded ${recStyle.bg} ${recStyle.text} border ${recStyle.border}`}
                  >
                    <RecIcon className="w-3 h-3" /> {recStyle.label}
                  </span>
                </div>
                <div className="text-right">
                  <span
                    className="text-sm font-mono font-bold"
                    style={{ color: pos.pnl >= 0 ? '#00d4aa' : '#ff4757' }}
                  >
                    {pos.pnl >= 0 ? '+' : ''}₹{pos.pnl.toFixed(0)} ({pos.pnl_pct >= 0 ? '+' : ''}{pos.pnl_pct.toFixed(1)}%)
                  </span>
                  <p className="text-[10px] text-[#546e7a]">
                    Avg ₹{pos.average_price?.toFixed(1)} → LTP ₹{pos.last_price?.toFixed(1)}
                    {pos.moneyness_pct != null && (
                      <span> · {pos.moneyness_pct >= 0 ? 'ITM' : 'OTM'} {Math.abs(pos.moneyness_pct).toFixed(2)}%</span>
                    )}
                  </p>
                </div>
              </div>

              {pos.alerts.length > 0 && (
                <div className="mt-2 space-y-1.5">
                  {pos.alerts.map((alert, j) => {
                    const style = ALERT_STYLES[alert.severity] || ALERT_STYLES.info;
                    return (
                      <div
                        key={j}
                        className={`${style.bg} border ${style.border} rounded p-2 text-[11px] ${style.text} flex items-start gap-1.5`}
                      >
                        <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                        {alert.message}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-[#546e7a] mt-3 italic">
        Shows every open NIFTY option position in your connected Zerodha account (however opened),
        cross-referenced against the current live signal AND actual strike vs live spot price.
        EXIT/BOOK PROFIT/MONITOR/HOLD is a definitive recommendation, not just a generic alert.
        Advisory only — never places or modifies orders.
      </p>
    </motion.div>
  );
}

// ── Live Equity Holdings ─────────────────────────────────────────────────────
// Shows your ACTUAL long-term equity holdings from Zerodha (separate from
// the F&O `positions` above) with live P&L, technical analysis, and a
// per-holding BUY_MORE/HOLD/TRIM/SELL suggestion. Fully optional — silently
// shows nothing if Zerodha isn't connected or there are no holdings.

const HOLDING_RECOMMENDATION_STYLES = {
  BUY_MORE: { bg: 'bg-[#00d4aa]/15', border: 'border-[#00d4aa]/50', text: 'text-[#00d4aa]', label: 'BUY MORE' },
  HOLD: { bg: 'bg-[#546e7a]/15', border: 'border-[#546e7a]/40', text: 'text-[#546e7a]', label: 'HOLD' },
  TRIM: { bg: 'bg-[#ffa502]/15', border: 'border-[#ffa502]/50', text: 'text-[#ffa502]', label: 'TRIM' },
  SELL: { bg: 'bg-[#ff4757]/15', border: 'border-[#ff4757]/50', text: 'text-[#ff4757]', label: 'SELL' },
};

function HoldingsCard() {
  const [data, setData] = useState(null);
  const [visible, setVisible] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchHoldings = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/holdings/live`);
      const json = await res.json();
      setData(json);
      setVisible(json.success && json.holding_count > 0);
    } catch (e) {
      setVisible(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHoldings();
    // Holdings change rarely (long-term positions) and each one requires a
    // yfinance fetch — poll much less frequently than live F&O positions.
    const interval = setInterval(fetchHoldings, 5 * 60000);
    return () => clearInterval(interval);
  }, [fetchHoldings]);

  if (!visible || !data) return null;

  const summary = data.portfolio_summary;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5"
    >
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide flex items-center gap-2">
          <Briefcase className="w-3.5 h-3.5" /> Equity Holdings
          <span className="text-[#e8eaf6] font-mono">({data.holding_count})</span>
          {loading && <RefreshCw className="w-3 h-3 animate-spin text-[#546e7a]" />}
        </p>
        <div className="text-right">
          <span
            className="text-sm font-mono font-bold"
            style={{ color: summary.total_pnl >= 0 ? '#00d4aa' : '#ff4757' }}
          >
            {summary.total_pnl >= 0 ? '+' : ''}₹{summary.total_pnl.toFixed(0)} ({summary.total_pnl_pct >= 0 ? '+' : ''}{summary.total_pnl_pct.toFixed(1)}%)
          </span>
          <p className="text-[10px] text-[#546e7a]">
            Invested ₹{summary.total_invested.toFixed(0)} → Now ₹{summary.total_current_value.toFixed(0)}
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {data.holdings.map((h, i) => {
          const recStyle = HOLDING_RECOMMENDATION_STYLES[h.recommendation] || HOLDING_RECOMMENDATION_STYLES.HOLD;
          return (
            <div key={i} className="bg-[#0a0e1a] border border-[#1a2035] rounded-xl p-3">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-3">
                  <span className="text-sm font-mono font-bold text-[#e8eaf6]">{h.tradingsymbol}</span>
                  <span className="text-xs text-[#546e7a]">× {h.quantity}</span>
                  <span
                    className={`inline-flex items-center gap-1 text-[10px] font-bold px-1.5 py-0.5 rounded ${recStyle.bg} ${recStyle.text} border ${recStyle.border}`}
                  >
                    {recStyle.label}
                  </span>
                  {h.technicals?.trend && (
                    <span className="text-[10px] text-[#546e7a]">
                      {h.technicals.trend} · RSI {h.technicals.rsi ?? '—'}
                    </span>
                  )}
                </div>
                <div className="text-right">
                  <span
                    className="text-sm font-mono font-bold"
                    style={{ color: h.pnl >= 0 ? '#00d4aa' : '#ff4757' }}
                  >
                    {h.pnl >= 0 ? '+' : ''}₹{h.pnl.toFixed(0)} ({h.pnl_pct >= 0 ? '+' : ''}{h.pnl_pct.toFixed(1)}%)
                  </span>
                  <p className="text-[10px] text-[#546e7a]">
                    Avg ₹{h.average_price?.toFixed(1)} → LTP ₹{h.last_price?.toFixed(1)}
                    {h.day_change_pct != null && (
                      <span style={{ color: h.day_change_pct >= 0 ? '#00d4aa' : '#ff4757' }}>
                        {' '}({h.day_change_pct >= 0 ? '+' : ''}{h.day_change_pct.toFixed(1)}% today)
                      </span>
                    )}
                  </p>
                </div>
              </div>

              {h.reasons?.length > 0 && (
                <div className="mt-2 space-y-1">
                  {h.reasons.map((r, j) => (
                    <p key={j} className="text-[11px] text-[#8892a6] flex items-start gap-1.5">
                      <span className="text-[#00d4aa] mt-0.5">•</span> {r.message}
                    </p>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <p className="text-[10px] text-[#546e7a] mt-3 italic">
        Shows every equity holding in your connected Zerodha account with live P&L and technical analysis
        (RSI, EMA trend, ADX — same engine used elsewhere in this app). BUY MORE/HOLD/TRIM/SELL combines
        your actual cost-basis P&L with the live technical setup. Advisory only — never places or modifies orders.
      </p>
    </motion.div>
  );
}

// ── GTT Orders (auto-trader exit orders) ────────────────────────────────────
// The auto-trader places a GTT OCO exit (SL + target) alongside every entry.
// This card shows all active GTTs so the user can see and cancel them —
// critical when manually closing a position (the GTT must be cancelled too,
// otherwise it fires on a position that no longer exists).

function GTTOrdersCard() {
  const [gtts, setGtts] = useState([]);
  const [visible, setVisible] = useState(false);
  const [cancelling, setCancelling] = useState(null);

  const fetchGtts = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/gtts`);
      const json = await res.json();
      const list = json.gtts || [];
      setGtts(list);
      setVisible(list.length > 0);
    } catch (e) {
      setVisible(false);
    }
  }, []);

  useEffect(() => {
    fetchGtts();
    const interval = setInterval(fetchGtts, 30000);
    return () => clearInterval(interval);
  }, [fetchGtts]);

  const cancelGtt = async (triggerId, symbol) => {
    if (!window.confirm(`Cancel GTT exit order for ${symbol}? The position will have NO automatic stop-loss or target exit.`)) return;
    setCancelling(triggerId);
    try {
      await fetch(`${API_BASE}/api/zerodha/gtt/${triggerId}`, { method: 'DELETE' });
      await fetchGtts();
    } catch (e) {
      alert('Failed to cancel GTT. Please cancel manually in Zerodha.');
    } finally {
      setCancelling(null);
    }
  };

  if (!visible || gtts.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-[#0f1629] border border-[#ffa502]/30 rounded-2xl p-5"
    >
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide flex items-center gap-2">
          <Target className="w-3.5 h-3.5 text-[#ffa502]" /> Active GTT Exit Orders
          <span className="text-[#e8eaf6] font-mono">({gtts.length})</span>
        </p>
        <p className="text-[10px] text-[#546e7a] italic">
          Auto-placed SL+target exits — cancel if you close the position manually
        </p>
      </div>

      <div className="space-y-2">
        {gtts.map((gtt) => {
          const symbol = gtt.condition?.tradingsymbol || gtt.tradingsymbol || '—';
          const orders = gtt.orders || [];
          const slOrder = orders.find(o => o.transaction_type === 'SELL' && orders.indexOf(o) === 0);
          const tgtOrder = orders.find(o => o.transaction_type === 'SELL' && orders.indexOf(o) === 1);
          const triggers = gtt.condition?.trigger_values || [];
          const slPrice = triggers[0];
          const tgtPrice = triggers[1];

          return (
            <div key={gtt.id} className="bg-[#0a0e1a] border border-[#1a2035] rounded-xl p-3 flex items-center justify-between gap-3 flex-wrap">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-sm font-mono font-bold text-[#e8eaf6]">{symbol}</span>
                <span className="text-[10px] bg-[#ffa502]/15 text-[#ffa502] border border-[#ffa502]/30 px-2 py-0.5 rounded font-bold uppercase">
                  {gtt.type || 'OCO'}
                </span>
                {slPrice != null && (
                  <span className="text-xs text-[#546e7a]">
                    SL: <span className="text-[#ff4757] font-mono font-bold">₹{slPrice}</span>
                  </span>
                )}
                {tgtPrice != null && (
                  <span className="text-xs text-[#546e7a]">
                    Target: <span className="text-[#00d4aa] font-mono font-bold">₹{tgtPrice}</span>
                  </span>
                )}
                <span className="text-[10px] text-[#546e7a]">
                  Status: <span className="text-[#e8eaf6]">{gtt.status || 'active'}</span>
                </span>
              </div>
              <button
                onClick={() => cancelGtt(gtt.id, symbol)}
                disabled={cancelling === gtt.id}
                className="flex items-center gap-1.5 text-xs text-[#ff4757] border border-[#ff4757]/30 bg-[#ff4757]/10 px-3 py-1.5 rounded hover:bg-[#ff4757]/20 transition disabled:opacity-50 flex-shrink-0"
              >
                {cancelling === gtt.id ? (
                  <RefreshCw className="w-3 h-3 animate-spin" />
                ) : (
                  <AlertTriangle className="w-3 h-3" />
                )}
                Cancel GTT
              </button>
            </div>
          );
        })}
      </div>
    </motion.div>
  );
}


// ── Main page ────────────────────────────────────────────────────────────────

export default function CASSignal() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [countdown, setCountdown] = useState(REFRESH_MS / 1000);
  const timerRef = useRef(null);
  const countdownRef = useRef(null);

  const fetchSignal = useCallback(async (force = false) => {
    setRefreshing(true);
    setError(null);
    try {
      const url = `${API_BASE}/api/cas-signal${force ? '?force_refresh=true' : ''}`;
      const res = await fetch(url);
      const json = await res.json();
      if (json.success === false) {
        setError(json.message || json.error || 'Unknown error');
      } else {
        setData(json);
      }
    } catch (e) {
      setError('Could not connect to backend. Make sure the server is running on port 8000.');
    } finally {
      setLoading(false);
      setRefreshing(false);
      // Reset countdown AND the auto-refresh interval so they stay in sync
      // after a manual refresh (otherwise the interval fires at the original
      // schedule while the countdown shows a different time).
      setCountdown(REFRESH_MS / 1000);
      clearInterval(timerRef.current);
      timerRef.current = setInterval(() => fetchSignal(false), REFRESH_MS);
    }
  }, []);

  useEffect(() => {
    fetchSignal();
    timerRef.current = setInterval(() => fetchSignal(false), REFRESH_MS);
    countdownRef.current = setInterval(() => {
      setCountdown((c) => (c > 0 ? c - 1 : 0));
    }, 1000);
    return () => {
      clearInterval(timerRef.current);
      clearInterval(countdownRef.current);
    };
  }, [fetchSignal]);

  const bigMoveColor =
    data?.risk_level === 'HIGH' ? '#ff4757' : data?.risk_level === 'MEDIUM' ? '#ffa502' : '#00d4aa';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-[#e8eaf6] flex items-center gap-2">
            <Gauge className="w-5 h-5 text-[#00d4aa]" />
            CAS Closing-Window Signal
          </h2>
          <p className="text-sm text-[#546e7a] mt-1">
            Live directional bias & big-move risk for the NSE Closing Auction Session
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-[#546e7a] flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" />
            {refreshing ? 'Refreshing…' : `Auto-refresh in ${countdown}s`}
          </span>
          <button
            onClick={() => fetchSignal(true)}
            disabled={refreshing}
            className="flex items-center gap-2 bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-4 py-2 rounded-xl text-sm hover:border-[#00d4aa] transition disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="bg-[#ff4757]/10 border border-[#ff4757]/30 rounded-2xl p-4 flex items-start gap-3"
          >
            <AlertTriangle className="w-5 h-5 text-[#ff4757] flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-[#ff4757] font-semibold text-sm">Could not fetch CAS signal</p>
              <p className="text-[#546e7a] text-xs mt-1">{error}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Loading skeleton */}
      {loading && (
        <div className="space-y-4 animate-pulse">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <SkeletonCard h="h-56" />
            <SkeletonCard h="h-56" />
          </div>
          <SkeletonCard h="h-24" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <SkeletonCard />
            <SkeletonCard />
          </div>
        </div>
      )}

      {/* Data */}
      {!loading && data && (
        <>
          {/* Warnings banner (partial degradation) */}
          <AnimatePresence>
            {data.warnings && data.warnings.length > 0 && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="bg-[#ffa502]/10 border border-[#ffa502]/30 rounded-xl p-3 flex items-start gap-2"
              >
                <AlertTriangle className="w-4 h-4 text-[#ffa502] flex-shrink-0 mt-0.5" />
                <div className="text-xs text-[#ffa502]">
                  {data.warnings.map((w, i) => <p key={i}>{w}</p>)}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* High conviction banner */}
          <AnimatePresence>
            {data.high_conviction_signal && (
              <HighConvictionBanner detail={data.high_conviction_detail} />
            )}
          </AnimatePresence>

          {/* Top row: bias + risk */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <BiasCard
              bias={data.directional_bias}
              confidence={data.directional_confidence}
              pop={data.directional_pop}
              strike={data.suggested_strike}
              action={data.suggested_action}
            />

            <motion.div
              layout
              className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-6 flex items-center justify-between"
            >
              <div>
                <p className="text-xs text-[#546e7a] uppercase tracking-wide font-semibold mb-2">
                  Big-Move Risk
                </p>
                <RiskBadge level={data.risk_level} />
                <p className="text-xs text-[#546e7a] mt-3">
                  Probability of an unusually large closing-window move today
                </p>
              </div>
              <CircularGauge
                value={data.big_move_probability}
                color={bigMoveColor}
                label="Big-Move POP"
                sublabel={data.big_move_pop != null ? `${Math.round(data.big_move_pop * 100)}% calibrated` : null}
              />
            </motion.div>
          </div>

          {/* Market context strip */}
          <motion.div
            layout
            className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-4 flex flex-wrap gap-6 text-sm"
          >
            <span className="text-[#546e7a]">
              Spot: <span className="text-[#e8eaf6] font-mono font-bold">
                {data.spot_price?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </span>
            </span>
            <span className="text-[#546e7a]">
              VIX: <span className="text-[#ffa502] font-mono font-bold">{data.vix?.toFixed(2)}</span>
            </span>
            {data.pcr != null && (
              <span className="text-[#546e7a]">
                PCR: <span className="text-[#e8eaf6] font-mono font-bold">{data.pcr}</span>
              </span>
            )}
            {data.max_pain != null && (
              <span className="text-[#546e7a]">
                Max Pain: <span className="text-[#e8eaf6] font-mono font-bold">{data.max_pain}</span>
              </span>
            )}
            {data.nearest_expiry && (
              <span className="text-[#546e7a]">
                Expiry: <span className="text-[#e8eaf6] font-mono font-bold">{data.nearest_expiry}</span>
                {data.days_to_expiry != null && (
                  <span className="text-[#546e7a]"> ({data.days_to_expiry}d)</span>
                )}
              </span>
            )}
            <span className="text-[#546e7a]">
              Intraday move: <span
                className="font-mono font-bold"
                style={{ color: data.intraday_main_move_pct >= 0 ? '#00d4aa' : '#ff4757' }}
              >
                {data.intraday_main_move_pct >= 0 ? '+' : ''}{data.intraday_main_move_pct?.toFixed(2)}%
              </span>
            </span>
          </motion.div>

          {/* Reasoning + OI */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ReasoningList items={data.reasoning} />

            <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5">
              <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide mb-3 flex items-center gap-2">
                <Target className="w-3.5 h-3.5" /> Top OI (Weekly Expiry)
              </p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-[10px] text-[#00d4aa] font-bold mb-1 flex items-center gap-1">
                    <TrendingUp className="w-3 h-3" /> CALLS
                  </p>
                  {data.top_call_oi?.slice(0, 5).map((c, i) => (
                    <OIRow key={i} item={c} type="CE" />
                  ))}
                </div>
                <div>
                  <p className="text-[10px] text-[#ff4757] font-bold mb-1 flex items-center gap-1">
                    <TrendingDown className="w-3 h-3" /> PUTS
                  </p>
                  {data.top_put_oi?.slice(0, 5).map((p, i) => (
                    <OIRow key={i} item={p} type="PE" />
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Live Positions & Risk Alerts (invisible unless Zerodha connected + open positions) */}
          <LivePositionsCard />

          {/* GTT Exit Orders — shows active auto-trader GTT OCO exits so user can cancel if needed */}
          <GTTOrdersCard />

          {/* Live Equity Holdings (invisible unless Zerodha connected + holdings exist) */}
          <HoldingsCard />

          {/* Honesty / model limitations footer */}
          <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5">
            <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide mb-2 flex items-center gap-2">
              <Info className="w-3.5 h-3.5" /> Model Performance & Limitations
            </p>
            <p className="text-xs text-[#8892a6] leading-relaxed">{data.model_honesty_note}</p>
            <p className="text-[10px] text-[#3a4356] mt-3 italic">{data.pop_explanation}</p>
          </div>

          <p className="text-center text-[10px] text-[#3a4356]">
            Last updated {new Date(data.timestamp).toLocaleTimeString()}
            {data.model_trained_at && ` · models trained ${new Date(data.model_trained_at).toLocaleString()}`}
          </p>
        </>
      )}
    </div>
  );
}