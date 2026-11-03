import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  RefreshCw, Clock, AlertTriangle, Info, Plus, X, CheckCircle2, Loader2,
  Wallet, TrendingUp, TrendingDown, Search,
} from 'lucide-react';

const API_BASE = 'http://localhost:8001';

const RECOMMENDATION_STYLES = {
  'BUY MORE': { bg: 'bg-[#00d4aa]/15', border: 'border-[#00d4aa]/50', text: 'text-[#00d4aa]' },
  'HOLD': { bg: 'bg-[#546e7a]/10', border: 'border-[#546e7a]/30', text: 'text-[#546e7a]' },
  'HOLD (review stop-loss)': { bg: 'bg-[#ffa502]/10', border: 'border-[#ffa502]/30', text: 'text-[#ffa502]' },
  'TRIM': { bg: 'bg-[#ffa502]/10', border: 'border-[#ffa502]/30', text: 'text-[#ffa502]' },
  'TRIM / REDUCE': { bg: 'bg-[#ff4757]/10', border: 'border-[#ff4757]/30', text: 'text-[#ff4757]' },
  'SELL': { bg: 'bg-[#ff4757]/15', border: 'border-[#ff4757]/50', text: 'text-[#ff4757]' },
};

function SkeletonCard() {
  return <div className="h-40 bg-[#0f1629] border border-[#1a2035] rounded-2xl animate-pulse" />;
}

function HoldingCard({ holding, onRemove }) {
  if (!holding.success) {
    return (
      <div className="bg-[#0f1629] border border-[#ff4757]/30 rounded-2xl p-5">
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-bold text-[#e8eaf6]">{holding.name}</p>
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#546e7a] font-mono">{holding.symbol}</span>
            <button
              onClick={() => { if (window.confirm(`Remove "${holding.name || holding.symbol}" from your eToro portfolio?`)) onRemove(holding.id); }}
              className="text-[#546e7a] hover:text-[#ff4757]"
              title="Remove holding"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
        <p className="text-xs text-[#ff4757] flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5" /> {holding.error || 'Could not fetch live data'}
        </p>
      </div>
    );
  }

  const recStyle = RECOMMENDATION_STYLES[holding.recommendation] || RECOMMENDATION_STYLES['HOLD'];
  const isProfitable = holding.pnl >= 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5 flex flex-col gap-3"
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-bold text-[#e8eaf6] flex items-center gap-1.5">
            {holding.name}
            <button
              onClick={() => { if (window.confirm(`Remove "${holding.name || holding.symbol}" from your eToro portfolio?`)) onRemove(holding.id); }}
              className="text-[#546e7a] hover:text-[#ff4757]"
              title="Remove holding"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </p>
          <p className="text-[11px] text-[#546e7a] font-mono">
            {holding.symbol} · {holding.quantity} @ {holding.entry_price?.toLocaleString('en-US', { maximumFractionDigits: 4 })}
          </p>
        </div>
        <div className="text-right">
          <p className="text-lg font-mono font-bold text-[#e8eaf6]">
            ${holding.spot?.toLocaleString('en-US', { maximumFractionDigits: 4 })}
          </p>
          <p className="text-xs font-mono" style={{ color: holding.day_change_pct >= 0 ? '#00d4aa' : '#ff4757' }}>
            {holding.day_change_pct >= 0 ? '+' : ''}{holding.day_change_pct?.toFixed(2)}% today
          </p>
        </div>
      </div>

      <div className={`${recStyle.bg} border ${recStyle.border} rounded-lg p-2.5`}>
        <span className={`inline-flex items-center gap-1.5 text-xs font-bold ${recStyle.text}`}>
          {isProfitable ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
          {holding.recommendation}
        </span>
        {holding.reasons?.map((r, i) => (
          <p key={i} className="text-[11px] text-[#8892a6] mt-1">{r}</p>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div className="bg-[#0a0e1a] border border-[#1a2035] rounded p-2">
          <p className="text-[9px] text-[#546e7a] uppercase">Invested</p>
          <p className="text-xs font-bold text-[#e8eaf6]">
            ${holding.invested?.toLocaleString('en-US', { maximumFractionDigits: 2 })}
          </p>
        </div>
        <div className="bg-[#0a0e1a] border border-[#1a2035] rounded p-2">
          <p className="text-[9px] text-[#546e7a] uppercase">Current Value</p>
          <p className="text-xs font-bold text-[#e8eaf6]">
            ${holding.current_value?.toLocaleString('en-US', { maximumFractionDigits: 2 })}
          </p>
        </div>
      </div>

      <div className="flex justify-between text-xs pt-2 border-t border-[#1a2035]">
        <span className="text-[#546e7a]">P&L</span>
        <span className="font-mono font-bold" style={{ color: isProfitable ? '#00d4aa' : '#ff4757' }}>
          {isProfitable ? '+$' : '-$'}{Math.abs(holding.pnl || 0).toLocaleString('en-US', { maximumFractionDigits: 2 })}
          {' '}({isProfitable ? '+' : ''}{holding.pnl_pct?.toFixed(2)}%)
        </span>
      </div>
    </motion.div>
  );
}

function AddHoldingCard({ onAdded }) {
  const [query, setQuery] = useState('');
  const [quantity, setQuantity] = useState('');
  const [entryPrice, setEntryPrice] = useState('');
  const [notes, setNotes] = useState('');
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState(null);
  const [adding, setAdding] = useState(false);
  const [addedMsg, setAddedMsg] = useState(null);
  const [error, setError] = useState(null);

  const handleValidate = async () => {
    const symbol = query.trim();
    if (!symbol) return;
    setValidating(true);
    setValidation(null);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/watchlist/search?symbol=${encodeURIComponent(symbol)}`);
      const json = await res.json();
      setValidation(json);
    } catch (e) {
      setValidation({ valid: false, error: 'Could not reach the backend.' });
    } finally {
      setValidating(false);
    }
  };

  const handleAdd = async () => {
    if (!validation?.valid || !quantity || !entryPrice) return;
    setAdding(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/etoro/holdings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: query.trim(),
          name: validation.name,
          quantity: parseFloat(quantity),
          entry_price: parseFloat(entryPrice),
          notes,
        }),
      });
      const json = await res.json();
      if (res.ok) {
        setAddedMsg(`Added ${json.name} (${json.symbol}) to your portfolio.`);
        setQuery(''); setQuantity(''); setEntryPrice(''); setNotes(''); setValidation(null);
        onAdded();
      } else {
        setError(json.detail || 'Failed to add holding');
      }
    } catch (e) {
      setError('Could not reach the backend.');
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5">
      <p className="text-sm font-bold text-[#e8eaf6] flex items-center gap-2 mb-3">
        <Plus className="w-4 h-4 text-[#00d4aa]" /> Record an eToro Holding
      </p>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
        <div className="md:col-span-1 flex gap-1">
          <input
            type="text"
            placeholder="Symbol e.g. AAPL"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setValidation(null); setAddedMsg(null); }}
            onKeyDown={(e) => e.key === 'Enter' && handleValidate()}
            className="flex-1 bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-sm text-[#e8eaf6] min-w-0"
          />
          <button
            onClick={handleValidate}
            disabled={validating || !query.trim()}
            className="flex-shrink-0 bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-2.5 rounded hover:border-[#00d4aa] transition disabled:opacity-50"
            title="Validate symbol"
          >
            {validating ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
          </button>
        </div>
        <input
          type="number"
          placeholder="Quantity"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          className="bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-sm text-[#e8eaf6]"
        />
        <input
          type="number"
          placeholder="Your entry price"
          value={entryPrice}
          onChange={(e) => setEntryPrice(e.target.value)}
          className="bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-sm text-[#e8eaf6]"
        />
        <input
          type="text"
          placeholder="Notes (optional)"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          className="bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-sm text-[#e8eaf6]"
        />
      </div>

      {validation && (
        <div className={`mt-3 rounded-lg p-3 text-xs flex items-center justify-between gap-3 ${
          validation.valid ? 'bg-[#00d4aa]/10 border border-[#00d4aa]/30' : 'bg-[#ff4757]/10 border border-[#ff4757]/30'
        }`}>
          {validation.valid ? (
            <>
              <span className="text-[#00d4aa] flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> Found: <span className="font-bold text-[#e8eaf6]">{validation.name}</span>
                {validation.resolved_symbol && validation.resolved_symbol !== query.trim().toUpperCase() && (
                  <span className="text-[#546e7a] font-mono">({validation.resolved_symbol})</span>
                )}
              </span>
              <button
                onClick={handleAdd}
                disabled={adding || !quantity || !entryPrice}
                className="flex items-center gap-1.5 bg-[#00d4aa]/15 border border-[#00d4aa]/40 text-[#00d4aa] px-3 py-1.5 rounded text-xs font-semibold hover:bg-[#00d4aa]/25 transition disabled:opacity-50 flex-shrink-0"
              >
                {adding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                Add Holding
              </button>
            </>
          ) : (
            <span className="text-[#ff4757] flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" /> {validation.error}
            </span>
          )}
        </div>
      )}

      {error && (
        <p className="mt-3 text-xs text-[#ff4757] flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5" /> {error}
        </p>
      )}
      {addedMsg && (
        <p className="mt-3 text-xs text-[#00d4aa] flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5" /> {addedMsg}
        </p>
      )}

      <p className="text-[10px] text-[#546e7a] mt-3">
        eToro has no self-serve public API for individual accounts (unlike Zerodha's Kite Connect) — confirmed
        by direct testing. So this is a manual portfolio tracker: enter what you actually hold on eToro (any
        symbol tradable there — stocks, ETFs, crypto pairs like BTC-USD) and get the same live technical
        analysis + P&L-aware suggestion used across this app.
      </p>
    </div>
  );
}

export default function Etoro() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const fetchPortfolio = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/etoro/portfolio`);
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
    }
  }, []);

  useEffect(() => {
    fetchPortfolio();
  }, [fetchPortfolio]);

  const handleRemove = useCallback(async (id) => {
    try {
      await fetch(`${API_BASE}/api/etoro/holdings/${id}`, { method: 'DELETE' });
      fetchPortfolio();
    } catch (e) {
      // Non-fatal
    }
  }, [fetchPortfolio]);

  const summary = data?.portfolio_summary;
  const isProfitable = summary && summary.total_pnl >= 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-[#e8eaf6] flex items-center gap-2">
            <Wallet className="w-5 h-5 text-[#00d4aa]" />
            eToro Portfolio Tracker
          </h2>
          <p className="text-sm text-[#546e7a] mt-1">
            Manually-tracked eToro holdings with live price, real P&L, and technical analysis
          </p>
        </div>
        <button
          onClick={fetchPortfolio}
          disabled={refreshing}
          className="flex items-center gap-2 bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-4 py-2 rounded-xl text-sm hover:border-[#00d4aa] transition disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="bg-[#0f1629] border border-[#ffa502]/30 rounded-2xl p-4 flex items-start gap-3">
        <Info className="w-5 h-5 text-[#ffa502] flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-[#ffa502] font-semibold text-sm">No live eToro API sync — manual entry only</p>
          <p className="text-[#546e7a] text-xs mt-1">
            eToro doesn't offer a self-serve public API for individual/retail accounts (unlike Zerodha's Kite
            Connect, which this app integrates with elsewhere). This tracker lets you manually record what you
            hold on eToro and still get real live price, P&L, and technical analysis for it.
          </p>
        </div>
      </div>

      {error && (
        <div className="bg-[#ff4757]/10 border border-[#ff4757]/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-[#ff4757] flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-[#ff4757] font-semibold text-sm">Could not fetch portfolio</p>
            <p className="text-[#546e7a] text-xs mt-1">{error}</p>
          </div>
        </div>
      )}

      <AddHoldingCard onAdded={fetchPortfolio} />

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {!loading && data && data.holding_count === 0 && (
        <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-8 text-center">
          <p className="text-sm text-[#546e7a]">No holdings recorded yet — add one above to get started.</p>
        </div>
      )}

      {!loading && data && data.holding_count > 0 && (
        <>
          {summary && (
            <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5">
              <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide mb-3 flex items-center gap-2">
                <Clock className="w-3.5 h-3.5" /> Portfolio Summary
              </p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div>
                  <p className="text-[10px] text-[#546e7a]">Invested</p>
                  <p className="text-sm font-mono font-bold text-[#e8eaf6]">
                    ${summary.total_invested.toLocaleString('en-US', { maximumFractionDigits: 2 })}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-[#546e7a]">Current Value</p>
                  <p className="text-sm font-mono font-bold text-[#e8eaf6]">
                    ${summary.total_current_value.toLocaleString('en-US', { maximumFractionDigits: 2 })}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-[#546e7a]">Total P&L</p>
                  <p className="text-sm font-mono font-bold" style={{ color: isProfitable ? '#00d4aa' : '#ff4757' }}>
                    {isProfitable ? '+$' : '-$'}{Math.abs(summary.total_pnl).toLocaleString('en-US', { maximumFractionDigits: 2 })}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] text-[#546e7a]">Total Return</p>
                  <p className="text-sm font-mono font-bold" style={{ color: isProfitable ? '#00d4aa' : '#ff4757' }}>
                    {isProfitable ? '+' : ''}{summary.total_pnl_pct.toFixed(2)}%
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.holdings.map((h) => (
              <HoldingCard key={h.id} holding={h} onRemove={handleRemove} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}