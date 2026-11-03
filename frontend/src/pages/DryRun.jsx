import React, { useState, useEffect, useCallback } from 'react';
import {
  FlaskConical, Loader, RefreshCw, TrendingUp, TrendingDown,
  Trash2, AlertTriangle, CheckCircle, Clock, XCircle, PlusCircle
} from 'lucide-react';

const API = 'http://localhost:8001';

function badge(signal) {
  return signal === 'BUY CE'
    ? 'bg-[#00d4aa]/10 text-[#00d4aa]'
    : 'bg-[#ff4757]/10 text-[#ff4757]';
}

function resultBadge(result) {
  if (result === 'WIN') return 'bg-[#00d4aa]/10 text-[#00d4aa]';
  if (result === 'LOSS') return 'bg-[#ff4757]/10 text-[#ff4757]';
  return 'bg-[#1a2035] text-[#546e7a]';
}

function exitReasonLabel(reason) {
  if (reason === 'TARGET') return { label: 'Target Hit', color: '#00d4aa' };
  if (reason === 'STOP_LOSS') return { label: 'Stop Loss', color: '#ff4757' };
  if (reason === 'EXPIRY') return { label: 'Expiry', color: '#ffa502' };
  return { label: reason || '—', color: '#546e7a' };
}

function SummaryCard({ label, value, sub, color = '#00d4aa' }) {
  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4">
      <p className="text-xs text-[#546e7a] mb-1">{label}</p>
      <p className="text-2xl font-bold font-mono" style={{ color }}>{value}</p>
      {sub && <p className="text-xs text-[#546e7a] mt-1">{sub}</p>}
    </div>
  );
}

function LivePnL({ trade, currentSpot }) {
  if (!currentSpot || trade.status !== 'OPEN') return null;
  const { entry_spot, signal, vix } = trade;
  const spotMove = Math.abs(currentSpot - entry_spot);
  const delta = 0.45;
  const vixMult = Math.max(0.5, (vix || 15) / 15);
  const premium = entry_spot * 0.015 * vixMult;
  const direction =
    signal === 'BUY CE'
      ? currentSpot > entry_spot ? 1 : -1
      : currentSpot < entry_spot ? -1 : 1;
  const pct = premium > 0
    ? Math.max(-100, Math.min(300, (direction * spotMove * delta / premium) * 100))
    : 0;
  const color = pct > 0 ? '#00d4aa' : pct < 0 ? '#ff4757' : '#546e7a';
  return (
    <span className="font-mono font-bold text-xs" style={{ color }}>
      {pct > 0 ? '+' : ''}{pct.toFixed(1)}%
    </span>
  );
}

export default function DryRun() {
  const [trades, setTrades] = useState([]);
  const [currentSignal, setCurrentSignal] = useState(null);
  const [currentSpot, setCurrentSpot] = useState(null);
  const [loading, setLoading] = useState(false);
  const [entering, setEntering] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [tab, setTab] = useState('open'); // 'open' | 'closed'

  const showSuccess = (msg) => {
    setSuccessMsg(msg);
    setTimeout(() => setSuccessMsg(null), 3000);
  };

  const fetchTrades = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/dry-run/trades`);
      const data = await res.json();
      setTrades(data.trades || []);
    } catch (e) {
      console.error('Failed to fetch trades', e);
    }
  }, []);

  const fetchSignal = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/signal`);
      const data = await res.json();
      setCurrentSignal(data);
      setCurrentSpot(data.spot);
    } catch (e) {
      console.error('Failed to fetch signal', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSignal();
    fetchTrades();
  }, [fetchSignal, fetchTrades]);

  const enterTrade = async () => {
    setEntering(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/dry-run/enter`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ notes: '' }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.detail || 'Failed to enter trade');
      } else {
        showSuccess(`Paper trade entered: ${data.trade.signal} @ ${data.trade.entry_spot?.toFixed(0)}`);
        fetchTrades();
      }
    } catch (e) {
      setError('Network error');
    } finally {
      setEntering(false);
    }
  };

  const updateTrades = async () => {
    setUpdating(true);
    setError(null);
    try {
      const res = await fetch(`${API}/api/dry-run/update`, { method: 'POST' });
      const data = await res.json();
      setCurrentSpot(data.current_spot);
      if (data.trades_closed > 0) {
        showSuccess(`${data.trades_closed} trade(s) closed. Spot: ${data.current_spot?.toFixed(0)}`);
      } else {
        showSuccess(`Updated. No trades closed. Spot: ${data.current_spot?.toFixed(0)}`);
      }
      fetchTrades();
    } catch (e) {
      setError('Update failed');
    } finally {
      setUpdating(false);
    }
  };

  const deleteTrade = async (id) => {
    if (!window.confirm('Delete this paper trade?')) return;
    await fetch(`${API}/api/dry-run/trades/${id}`, { method: 'DELETE' });
    fetchTrades();
  };

  const clearAll = async () => {
    if (!window.confirm('Delete ALL paper trades? This cannot be undone.')) return;
    await fetch(`${API}/api/dry-run/trades`, { method: 'DELETE' });
    fetchTrades();
  };

  const openTrades = trades.filter(t => t.status === 'OPEN');
  const closedTrades = trades.filter(t => t.status === 'CLOSED');

  // Summary stats from closed trades
  const wins = closedTrades.filter(t => t.result === 'WIN');
  const losses = closedTrades.filter(t => t.result === 'LOSS');
  const winRate = closedTrades.length > 0 ? (wins.length / closedTrades.length * 100) : 0;
  const avgReturn = closedTrades.length > 0
    ? closedTrades.reduce((s, t) => s + (t.pct_return || 0), 0) / closedTrades.length
    : 0;
  const bestTrade = closedTrades.length > 0 ? Math.max(...closedTrades.map(t => t.pct_return || 0)) : 0;
  const worstTrade = closedTrades.length > 0 ? Math.min(...closedTrades.map(t => t.pct_return || 0)) : 0;

  const canEnter = currentSignal &&
    currentSignal.signal !== 'STAY OUT' &&
    (currentSignal.dte ?? 99) >= 2;

  return (
    <div className="space-y-6">

      {/* Header + actions */}
      <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h2 className="text-lg font-bold text-[#e8eaf6] flex items-center gap-2">
              <FlaskConical className="w-5 h-5 text-[#ffa502]" />
              Dry Run — Paper Trading
            </h2>
            <p className="text-xs text-[#546e7a] mt-1">
              Enter paper trades based on live signals. No real money involved.
            </p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <button
              onClick={fetchSignal}
              disabled={loading}
              className="bg-[#1a2035] text-[#546e7a] px-3 py-2 rounded text-sm flex items-center gap-2 hover:text-[#e8eaf6] transition disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              Refresh Signal
            </button>
            <button
              onClick={updateTrades}
              disabled={updating || openTrades.length === 0}
              className="bg-[#1a2035] text-[#546e7a] px-3 py-2 rounded text-sm flex items-center gap-2 hover:text-[#e8eaf6] transition disabled:opacity-50"
              title="Check current price against open trades"
            >
              {updating ? <Loader className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              Update Open Trades
            </button>
            {trades.length > 0 && (
              <button
                onClick={clearAll}
                className="bg-[#ff4757]/10 text-[#ff4757] px-3 py-2 rounded text-sm flex items-center gap-2 hover:bg-[#ff4757]/20 transition"
              >
                <Trash2 className="w-4 h-4" />
                Clear All
              </button>
            )}
          </div>
        </div>

        {/* Feedback messages */}
        {error && (
          <div className="mt-4 flex items-center gap-2 text-sm text-[#ff4757] bg-[#ff4757]/10 px-4 py-2 rounded">
            <XCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}
        {successMsg && (
          <div className="mt-4 flex items-center gap-2 text-sm text-[#00d4aa] bg-[#00d4aa]/10 px-4 py-2 rounded">
            <CheckCircle className="w-4 h-4 flex-shrink-0" />
            {successMsg}
          </div>
        )}
      </div>

      {/* Current Signal Card */}
      {currentSignal && (
        <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
          <h3 className="text-sm font-bold text-[#546e7a] uppercase tracking-wider mb-4">Current Live Signal</h3>
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-6 flex-wrap">
              <div>
                <p className="text-xs text-[#546e7a] mb-1">Signal</p>
                <span className={`text-lg font-bold font-mono px-3 py-1 rounded ${
                  currentSignal.signal === 'BUY CE'
                    ? 'bg-[#00d4aa]/10 text-[#00d4aa]'
                    : currentSignal.signal === 'BUY PE'
                    ? 'bg-[#ff4757]/10 text-[#ff4757]'
                    : 'bg-[#1a2035] text-[#546e7a]'
                }`}>
                  {currentSignal.signal}
                </span>
              </div>
              <div>
                <p className="text-xs text-[#546e7a] mb-1">Confidence</p>
                <p className="text-lg font-bold font-mono text-[#e8eaf6]">{currentSignal.confidence?.toFixed(0)}%</p>
              </div>
              <div>
                <p className="text-xs text-[#546e7a] mb-1">Spot</p>
                <p className="text-lg font-bold font-mono text-[#e8eaf6]">{currentSignal.spot?.toFixed(0)}</p>
              </div>
              <div>
                <p className="text-xs text-[#546e7a] mb-1">VIX</p>
                <p className="text-lg font-bold font-mono text-[#e8eaf6]">{currentSignal.vix?.toFixed(1)}</p>
              </div>
              <div>
                <p className="text-xs text-[#546e7a] mb-1">DTE</p>
                <p className={`text-lg font-bold font-mono ${
                  (currentSignal.dte ?? 99) < 2 ? 'text-[#ff4757]' :
                  (currentSignal.dte ?? 99) <= 3 ? 'text-[#ffa502]' : 'text-[#e8eaf6]'
                }`}>
                  {currentSignal.dte ?? '—'}
                  <span className="text-xs text-[#546e7a] ml-1">days</span>
                </p>
              </div>
              <div>
                <p className="text-xs text-[#546e7a] mb-1">Next Expiry</p>
                <p className="text-sm font-mono text-[#546e7a]">{currentSignal.next_expiry}</p>
              </div>
            </div>

            <button
              onClick={enterTrade}
              disabled={entering || !canEnter}
              className={`px-5 py-2.5 rounded font-semibold flex items-center gap-2 transition text-sm ${
                canEnter
                  ? 'bg-[#ffa502] text-[#0a0e1a] hover:bg-[#ffa502]/90'
                  : 'bg-[#1a2035] text-[#546e7a] cursor-not-allowed'
              } disabled:opacity-60`}
              title={
                !canEnter
                  ? currentSignal.signal === 'STAY OUT'
                    ? 'Signal is STAY OUT'
                    : 'DTE < 2 — too close to expiry'
                  : 'Enter paper trade at current signal'
              }
            >
              {entering ? <Loader className="w-4 h-4 animate-spin" /> : <PlusCircle className="w-4 h-4" />}
              Enter Paper Trade
            </button>
          </div>

          {!canEnter && currentSignal.signal !== 'STAY OUT' && (currentSignal.dte ?? 99) < 2 && (
            <div className="mt-3 flex items-center gap-2 text-xs text-[#ffa502] bg-[#ffa502]/10 px-3 py-2 rounded">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              DTE = {currentSignal.dte} — too close to expiry. Trades skipped to avoid theta decay.
            </div>
          )}
        </div>
      )}

      {/* Summary stats (closed trades only) */}
      {closedTrades.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SummaryCard
            label="Paper Win Rate"
            value={`${winRate.toFixed(1)}%`}
            sub={`${wins.length}W / ${losses.length}L`}
            color={winRate >= 55 ? '#00d4aa' : winRate >= 45 ? '#ffa502' : '#ff4757'}
          />
          <SummaryCard
            label="Avg Return"
            value={`${avgReturn > 0 ? '+' : ''}${avgReturn.toFixed(1)}%`}
            sub="per closed trade"
            color={avgReturn >= 0 ? '#00d4aa' : '#ff4757'}
          />
          <SummaryCard
            label="Best Trade"
            value={`+${bestTrade.toFixed(1)}%`}
            color="#00d4aa"
          />
          <SummaryCard
            label="Worst Trade"
            value={`${worstTrade.toFixed(1)}%`}
            color="#ff4757"
          />
        </div>
      )}

      {/* Tabs */}
      <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg overflow-hidden">
        <div className="flex border-b border-[#1a2035]">
          <button
            onClick={() => setTab('open')}
            className={`px-6 py-3 text-sm font-semibold flex items-center gap-2 transition ${
              tab === 'open'
                ? 'text-[#00d4aa] border-b-2 border-[#00d4aa] bg-[#00d4aa]/5'
                : 'text-[#546e7a] hover:text-[#e8eaf6]'
            }`}
          >
            <Clock className="w-4 h-4" />
            Open Trades
            {openTrades.length > 0 && (
              <span className="bg-[#ffa502] text-[#0a0e1a] text-xs font-bold px-1.5 py-0.5 rounded-full">
                {openTrades.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setTab('closed')}
            className={`px-6 py-3 text-sm font-semibold flex items-center gap-2 transition ${
              tab === 'closed'
                ? 'text-[#00d4aa] border-b-2 border-[#00d4aa] bg-[#00d4aa]/5'
                : 'text-[#546e7a] hover:text-[#e8eaf6]'
            }`}
          >
            <CheckCircle className="w-4 h-4" />
            Closed Trades
            {closedTrades.length > 0 && (
              <span className="bg-[#1a2035] text-[#546e7a] text-xs font-bold px-1.5 py-0.5 rounded-full">
                {closedTrades.length}
              </span>
            )}
          </button>
        </div>

        <div className="p-6">
          {/* Open Trades */}
          {tab === 'open' && (
            openTrades.length === 0 ? (
              <div className="text-center py-10 text-[#546e7a]">
                <FlaskConical className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p>No open paper trades</p>
                <p className="text-xs mt-1">Enter a trade using the current signal above</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#1a2035]">
                      <th className="text-left py-2 text-[#546e7a]">Date</th>
                      <th className="text-left py-2 text-[#546e7a]">Signal</th>
                      <th className="text-left py-2 text-[#546e7a]">Strike</th>
                      <th className="text-right py-2 text-[#546e7a]">Entry</th>
                      <th className="text-right py-2 text-[#546e7a]">SL</th>
                      <th className="text-right py-2 text-[#546e7a]">Target</th>
                      <th className="text-right py-2 text-[#546e7a]">DTE</th>
                      <th className="text-right py-2 text-[#546e7a]">Max Hold</th>
                      <th className="text-right py-2 text-[#546e7a]">Live P&L</th>
                      <th className="text-center py-2 text-[#546e7a]">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {openTrades.map(trade => (
                      <tr key={trade.id} className="border-b border-[#1a2035] hover:bg-[#1a2035] transition">
                        <td className="py-2 text-[#546e7a] text-xs">{trade.entry_date}</td>
                        <td className="py-2">
                          <span className={`text-xs font-bold font-mono px-2 py-0.5 rounded ${badge(trade.signal)}`}>
                            {trade.signal}
                          </span>
                        </td>
                        <td className="py-2 text-[#e8eaf6] font-mono text-xs">{trade.strike}</td>
                        <td className="py-2 text-right font-mono text-[#e8eaf6] text-xs">{trade.entry_spot?.toFixed(0)}</td>
                        <td className="py-2 text-right font-mono text-[#ff4757] text-xs">{trade.sl?.toFixed(0)}</td>
                        <td className="py-2 text-right font-mono text-[#00d4aa] text-xs">{trade.target?.toFixed(0)}</td>
                        <td className="py-2 text-right font-mono text-xs"
                            style={{ color: trade.dte <= 3 ? '#ffa502' : '#546e7a' }}>
                          {trade.dte}
                        </td>
                        <td className="py-2 text-right text-[#546e7a] text-xs">{trade.max_hold_days}d</td>
                        <td className="py-2 text-right">
                          <LivePnL trade={trade} currentSpot={currentSpot} />
                        </td>
                        <td className="py-2 text-center">
                          <button
                            onClick={() => deleteTrade(trade.id)}
                            className="text-[#546e7a] hover:text-[#ff4757] transition p-1"
                            title="Delete trade"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="text-xs text-[#546e7a] mt-3">
                  Live P&L is estimated from current spot. Click "Update Open Trades" to check for target/SL hits.
                </p>
              </div>
            )
          )}

          {/* Closed Trades */}
          {tab === 'closed' && (
            closedTrades.length === 0 ? (
              <div className="text-center py-10 text-[#546e7a]">
                <CheckCircle className="w-10 h-10 mx-auto mb-3 opacity-30" />
                <p>No closed trades yet</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-[#1a2035]">
                      <th className="text-left py-2 text-[#546e7a]">Entry Date</th>
                      <th className="text-left py-2 text-[#546e7a]">Signal</th>
                      <th className="text-left py-2 text-[#546e7a]">Strike</th>
                      <th className="text-right py-2 text-[#546e7a]">Entry</th>
                      <th className="text-right py-2 text-[#546e7a]">Exit</th>
                      <th className="text-left py-2 text-[#546e7a]">Exit Reason</th>
                      <th className="text-right py-2 text-[#546e7a]">Return</th>
                      <th className="text-center py-2 text-[#546e7a]">Result</th>
                      <th className="text-center py-2 text-[#546e7a]">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {closedTrades.map(trade => {
                      const { label, color } = exitReasonLabel(trade.exit_reason);
                      return (
                        <tr key={trade.id} className="border-b border-[#1a2035] hover:bg-[#1a2035] transition">
                          <td className="py-2 text-[#546e7a] text-xs">{trade.entry_date}</td>
                          <td className="py-2">
                            <span className={`text-xs font-bold font-mono px-2 py-0.5 rounded ${badge(trade.signal)}`}>
                              {trade.signal}
                            </span>
                          </td>
                          <td className="py-2 text-[#e8eaf6] font-mono text-xs">{trade.strike}</td>
                          <td className="py-2 text-right font-mono text-[#e8eaf6] text-xs">{trade.entry_spot?.toFixed(0)}</td>
                          <td className="py-2 text-right font-mono text-[#e8eaf6] text-xs">{trade.exit_spot?.toFixed(0)}</td>
                          <td className="py-2 text-xs font-mono" style={{ color }}>{label}</td>
                          <td className={`py-2 text-right font-mono font-bold text-xs ${
                            (trade.pct_return || 0) > 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]'
                          }`}>
                            {(trade.pct_return || 0) > 0 ? '+' : ''}{(trade.pct_return || 0).toFixed(1)}%
                          </td>
                          <td className="py-2 text-center">
                            <span className={`text-xs font-bold px-2 py-0.5 rounded ${resultBadge(trade.result)}`}>
                              {trade.result || '—'}
                            </span>
                          </td>
                          <td className="py-2 text-center">
                            <button
                              onClick={() => deleteTrade(trade.id)}
                              className="text-[#546e7a] hover:text-[#ff4757] transition p-1"
                              title="Delete trade"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}
