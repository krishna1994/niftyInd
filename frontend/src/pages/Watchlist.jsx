import React, { useState, useEffect, useCallback } from 'react';
import { motion } from 'framer-motion';
import {
  RefreshCw, Clock, AlertTriangle,
  ShieldCheck, ArrowUpCircle, ArrowDownCircle,
  PauseCircle, Info, Search, Plus, X, CheckCircle2, Loader2,
} from 'lucide-react';

const API_BASE = 'http://localhost:8001';

// Styling for the combined short-term + long-term recommendation
const RECOMMENDATION_STYLES = {
  'STRONG BUY': { bg: 'bg-[#00d4aa]/15', border: 'border-[#00d4aa]/50', text: 'text-[#00d4aa]', icon: ArrowUpCircle },
  'BUY (counter-trend — caution)': { bg: 'bg-[#00d4aa]/10', border: 'border-[#00d4aa]/30', text: 'text-[#00d4aa]', icon: ArrowUpCircle },
  'AVOID / TRIM': { bg: 'bg-[#ff4757]/15', border: 'border-[#ff4757]/50', text: 'text-[#ff4757]', icon: ArrowDownCircle },
  'HOLD (pullback in uptrend)': { bg: 'bg-[#ffa502]/10', border: 'border-[#ffa502]/30', text: 'text-[#ffa502]', icon: PauseCircle },
  'HOLD / ACCUMULATE ON DIPS': { bg: 'bg-[#00d4aa]/10', border: 'border-[#00d4aa]/30', text: 'text-[#00d4aa]', icon: PauseCircle },
  'HOLD / WAIT FOR TREND REVERSAL': { bg: 'bg-[#ff4757]/10', border: 'border-[#ff4757]/30', text: 'text-[#ff4757]', icon: PauseCircle },
  'HOLD/WATCH': { bg: 'bg-[#546e7a]/10', border: 'border-[#546e7a]/30', text: 'text-[#546e7a]', icon: PauseCircle },
};

function SkeletonCard() {
  return <div className="h-44 bg-[#0f1629] border border-[#1a2035] rounded-2xl animate-pulse" />;
}

function StockCard({ stock, onRemove }) {
  if (!stock.success) {
    return (
      <div className="bg-[#0f1629] border border-[#ff4757]/30 rounded-2xl p-5">
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-bold text-[#e8eaf6]">{stock.name}</p>
          <div className="flex items-center gap-2">
            <span className="text-xs text-[#546e7a] font-mono">{stock.symbol}</span>
            {stock.is_custom && (
              <button onClick={() => onRemove(stock.symbol)} className="text-[#546e7a] hover:text-[#ff4757]" title="Remove from watchlist">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
        <p className="text-xs text-[#ff4757] flex items-center gap-1.5">
          <AlertTriangle className="w-3.5 h-3.5" /> {stock.error || 'Could not fetch live data'}
        </p>
      </div>
    );
  }

  const recStyle = RECOMMENDATION_STYLES[stock.recommendation] || RECOMMENDATION_STYLES['HOLD/WATCH'];
  const RecIcon = recStyle.icon;
  const trendColor = stock.long_term_trend === 'BULLISH' ? '#00d4aa' : stock.long_term_trend === 'BEARISH' ? '#ff4757' : '#546e7a';

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5 flex flex-col gap-3"
    >
      {/* Header: name, symbol, price */}
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-bold text-[#e8eaf6] flex items-center gap-1.5">
            {stock.name}
            {stock.is_custom && (
              <button onClick={() => onRemove(stock.symbol)} className="text-[#546e7a] hover:text-[#ff4757]" title="Remove from watchlist">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </p>
          <p className="text-[11px] text-[#546e7a] font-mono">{stock.symbol}</p>
        </div>
        <div className="text-right">
          <p className="text-lg font-mono font-bold text-[#e8eaf6]">
            ${stock.spot?.toLocaleString('en-US', { maximumFractionDigits: 2 })}
          </p>
          <p className="text-xs font-mono" style={{ color: stock.day_change_pct >= 0 ? '#00d4aa' : '#ff4757' }}>
            {stock.day_change_pct >= 0 ? '+' : ''}{stock.day_change_pct?.toFixed(2)}% today
          </p>
        </div>
      </div>

      {/* Combined recommendation badge */}
      <div className={`${recStyle.bg} border ${recStyle.border} rounded-lg p-2.5`}>
        <span className={`inline-flex items-center gap-1.5 text-xs font-bold ${recStyle.text}`}>
          <RecIcon className="w-3.5 h-3.5" /> {stock.recommendation}
        </span>
        <p className="text-[11px] text-[#8892a6] mt-1">{stock.recommendation_reason}</p>
      </div>

      {/* Short-term vs long-term split */}
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-[#0a0e1a] border border-[#1a2035] rounded p-2">
          <p className="text-[9px] text-[#546e7a] uppercase">Short-Term Swing</p>
          <p className="text-xs font-bold" style={{ color: stock.swing_action === 'BUY' ? '#00d4aa' : stock.swing_action === 'SELL/AVOID' ? '#ff4757' : '#ffa502' }}>
            {stock.swing_action}
          </p>
          <p className="text-[10px] text-[#546e7a]">
            Bull {stock.bull_confidence}% / Bear {stock.bear_confidence}%
          </p>
        </div>
        <div className="bg-[#0a0e1a] border border-[#1a2035] rounded p-2">
          <p className="text-[9px] text-[#546e7a] uppercase">Long-Term Trend</p>
          <p className="text-xs font-bold" style={{ color: trendColor }}>{stock.long_term_trend}</p>
          <p className="text-[10px] text-[#546e7a]">
            {stock.pct_from_200ema != null ? `${stock.pct_from_200ema >= 0 ? '+' : ''}${stock.pct_from_200ema}% vs 200-EMA` : '—'}
          </p>
        </div>
      </div>

      {/* 52-week range + 1yr return */}
      <div className="flex justify-between text-[10px] text-[#546e7a]">
        <span>52w: ${stock.low_52w?.toLocaleString('en-US')} - ${stock.high_52w?.toLocaleString('en-US')}</span>
        {stock.one_year_return_pct != null && (
          <span style={{ color: stock.one_year_return_pct >= 0 ? '#00d4aa' : '#ff4757' }}>
            1yr: {stock.one_year_return_pct >= 0 ? '+' : ''}{stock.one_year_return_pct}%
          </span>
        )}
      </div>

      {/* Suggested SL/target for swing action, only if there is one */}
      {stock.suggested_stop_loss != null && (
        <div className="flex justify-between text-[10px] pt-2 border-t border-[#1a2035]">
          <span className="text-[#ff4757]">SL: ${stock.suggested_stop_loss?.toLocaleString('en-US')}</span>
          <span className="text-[#00d4aa]">Target: ${stock.suggested_target?.toLocaleString('en-US')}</span>
        </div>
      )}

      {/* Indicator context */}
      <p className="text-[10px] text-[#8892a6]">
        RSI {stock.rsi ?? '—'} · ADX {stock.adx ?? '—'} · {stock.macd_label}
      </p>
    </motion.div>
  );
}

// ── Search & Add custom symbol ───────────────────────────────────────────────
// Lets the user look up ANY ticker (validated live against yfinance before
// being added) and get the exact same swing + long-term signal analysis as
// the built-in watchlist. Two-step flow: search validates without
// persisting, add actually saves it (survives restarts) and triggers a
// watchlist refresh so the new card shows up immediately.

function SearchAddCard({ onAdded }) {
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState(null); // {valid, name, error}
  const [adding, setAdding] = useState(false);
  const [addedMsg, setAddedMsg] = useState(null);

  // Live autocomplete suggestions — debounced as the user types (company
  // name OR partial ticker), backed by /api/watchlist/suggest.
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestLoading, setSuggestLoading] = useState(false);
  const debounceRef = React.useRef(null);
  const wrapperRef = React.useRef(null);

  const fetchSuggestions = useCallback(async (text) => {
    if (!text || text.trim().length < 2) {
      setSuggestions([]);
      return;
    }
    setSuggestLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/watchlist/suggest?q=${encodeURIComponent(text.trim())}`);
      const json = await res.json();
      setSuggestions(json.suggestions || []);
    } catch (e) {
      setSuggestions([]);
    } finally {
      setSuggestLoading(false);
    }
  }, []);

  const handleInputChange = (value) => {
    setQuery(value);
    setResult(null);
    setAddedMsg(null);
    setShowSuggestions(true);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchSuggestions(value), 300);
  };

  // Close the suggestions dropdown when clicking anywhere outside it
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSearch = async (overrideSymbol) => {
    const symbol = (overrideSymbol || query).trim();
    if (!symbol) return;
    setShowSuggestions(false);
    setSearching(true);
    setResult(null);
    setAddedMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/watchlist/search?symbol=${encodeURIComponent(symbol)}`);
      const json = await res.json();
      setResult(json);
    } catch (e) {
      setResult({ valid: false, name: null, error: 'Could not reach the backend.' });
    } finally {
      setSearching(false);
    }
  };

  const handleSuggestionClick = (suggestion) => {
    setQuery(suggestion.symbol);
    setShowSuggestions(false);
    setSuggestions([]);
    handleSearch(suggestion.symbol);
  };

  const handleAdd = async () => {
    if (!result?.valid) return;
    setAdding(true);
    try {
      const res = await fetch(`${API_BASE}/api/watchlist/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: query.trim(), name: result.name }),
      });
      const json = await res.json();
      if (res.ok) {
        setAddedMsg(`Added ${json.name} (${json.symbol}) — refreshing watchlist...`);
        setQuery('');
        setResult(null);
        onAdded();
      } else {
        setResult({ valid: false, name: null, error: json.detail || 'Failed to add symbol' });
      }
    } catch (e) {
      setResult({ valid: false, name: null, error: 'Could not reach the backend.' });
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5">
      <p className="text-sm font-bold text-[#e8eaf6] flex items-center gap-2 mb-3">
        <Search className="w-4 h-4 text-[#00d4aa]" /> Search & Add Any Stock Symbol
      </p>
      <div className="flex items-center gap-2 relative" ref={wrapperRef}>
        <input
          type="text"
          placeholder="e.g. AAPL, TSLA, RELIANCE.NS, 7203.T, or type a company name"
          value={query}
          onChange={(e) => handleInputChange(e.target.value)}
          onFocus={() => query.trim().length >= 2 && setShowSuggestions(true)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          className="flex-1 bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-sm text-[#e8eaf6]"
        />
        <button
          onClick={() => handleSearch()}
          disabled={searching || !query.trim()}
          className="flex items-center gap-1.5 bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-4 py-2 rounded text-sm hover:border-[#00d4aa] transition disabled:opacity-50 flex-shrink-0"
        >
          {searching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
          Search
        </button>

        {/* Autocomplete dropdown — company name or ticker, live from Yahoo Finance search */}
        {showSuggestions && (suggestions.length > 0 || suggestLoading) && (
          <div className="absolute top-full left-0 right-[92px] mt-1 bg-[#1a2035] border border-[#00d4aa]/30 rounded-lg shadow-lg z-10 max-h-64 overflow-y-auto">
            {suggestLoading && (
              <div className="px-3 py-2 text-xs text-[#546e7a] flex items-center gap-1.5">
                <Loader2 className="w-3 h-3 animate-spin" /> Searching…
              </div>
            )}
            {!suggestLoading && suggestions.map((s) => (
              <button
                key={s.symbol}
                onClick={() => handleSuggestionClick(s)}
                className="w-full text-left px-3 py-2 hover:bg-[#0f1629] transition flex items-center justify-between gap-2 border-b border-[#0a0e1a] last:border-b-0"
              >
                <div className="min-w-0">
                  <p className="text-xs font-bold text-[#e8eaf6] truncate">{s.name}</p>
                  <p className="text-[10px] text-[#546e7a]">{s.exchange} · {s.type}</p>
                </div>
                <span className="text-xs font-mono text-[#00d4aa] flex-shrink-0">{s.symbol}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {result && (
        <div className={`mt-3 rounded-lg p-3 text-xs flex items-center justify-between gap-3 ${
          result.valid ? 'bg-[#00d4aa]/10 border border-[#00d4aa]/30' : 'bg-[#ff4757]/10 border border-[#ff4757]/30'
        }`}>
          {result.valid ? (
            <>
              <span className="text-[#00d4aa] flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> Found: <span className="font-bold text-[#e8eaf6]">{result.name}</span>
                {result.resolved_symbol && result.resolved_symbol !== query.trim().toUpperCase() && (
                  <span className="text-[#546e7a] font-mono">({result.resolved_symbol})</span>
                )}
              </span>
              <button
                onClick={handleAdd}
                disabled={adding}
                className="flex items-center gap-1.5 bg-[#00d4aa]/15 border border-[#00d4aa]/40 text-[#00d4aa] px-3 py-1.5 rounded text-xs font-semibold hover:bg-[#00d4aa]/25 transition disabled:opacity-50 flex-shrink-0"
              >
                {adding ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                Add to Watchlist
              </button>
            </>
          ) : (
            <span className="text-[#ff4757] flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" /> {result.error}
            </span>
          )}
        </div>
      )}

      {addedMsg && (
        <p className="mt-3 text-xs text-[#00d4aa] flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5" /> {addedMsg}
        </p>
      )}

      <p className="text-[10px] text-[#546e7a] mt-3">
        Works with any yfinance-recognized symbol — US stocks (AAPL), ETFs (SPY), Indian stocks with .NS/.BO suffix
        (RELIANCE.NS), or other exchanges (7203.T for Tokyo). Validated live before adding — a typo'd symbol will
        never get silently added as a permanent error card.
      </p>
    </div>
  );
}

export default function Watchlist() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const fetchWatchlist = useCallback(async (force = false) => {
    setRefreshing(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/watchlist${force ? '?force_refresh=true' : ''}`);
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
    fetchWatchlist();
    // 5-minute auto-refresh — matches the backend's own cache window, so
    // this never fetches stale-vs-fresh data pointlessly.
    const interval = setInterval(() => fetchWatchlist(false), 5 * 60000);
    return () => clearInterval(interval);
  }, [fetchWatchlist]);

  const handleRemove = useCallback(async (symbol) => {
    try {
      await fetch(`${API_BASE}/api/watchlist/${encodeURIComponent(symbol)}`, { method: 'DELETE' });
      fetchWatchlist(true);
    } catch (e) {
      // Non-fatal — the card just won't disappear until the next successful refresh
    }
  }, [fetchWatchlist]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-[#e8eaf6] flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-[#00d4aa]" />
            Global Stocks Watchlist
          </h2>
          <p className="text-sm text-[#546e7a] mt-1">
            Live tracker + swing signal + long-term trend for a fixed set of global stocks/ETFs
          </p>
        </div>
        <div className="flex items-center gap-3">
          {data?.timestamp && (
            <span className="text-xs text-[#546e7a] flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              {refreshing ? 'Refreshing…' : `Updated ${new Date(data.timestamp).toLocaleTimeString()}`}
            </span>
          )}
          <button
            onClick={() => fetchWatchlist(true)}
            disabled={refreshing}
            className="flex items-center gap-2 bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-4 py-2 rounded-xl text-sm hover:border-[#00d4aa] transition disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-[#ff4757]/10 border border-[#ff4757]/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-[#ff4757] flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-[#ff4757] font-semibold text-sm">Could not fetch watchlist</p>
            <p className="text-[#546e7a] text-xs mt-1">{error}</p>
          </div>
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 11 }).map((_, i) => <SkeletonCard key={i} />)}
        </div>
      )}

      {!loading && data && (
        <>
          <SearchAddCard onAdded={() => fetchWatchlist(true)} />

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data.watchlist?.map((stock) => (
              <StockCard key={stock.symbol} stock={stock} onRemove={handleRemove} />
            ))}
          </div>

          <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5">
            <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide mb-2 flex items-center gap-2">
              <Info className="w-3.5 h-3.5" /> How to Read This
            </p>
            <p className="text-xs text-[#8892a6] leading-relaxed">
              <span className="text-[#e8eaf6] font-semibold">Short-Term Swing</span> uses the SAME technical engine
              (MACD + Supertrend + Candle Pattern, empirically weighted from backtesting) as the main NIFTY signal —
              a multi-day view suitable for swing trading. <span className="text-[#e8eaf6] font-semibold">Long-Term
              Trend</span> is purely price vs the 200-day EMA — the classic long-term trend filter. The combined{' '}
              <span className="text-[#e8eaf6] font-semibold">recommendation</span> reconciles both: e.g. a short-term
              dip within a still-bullish long-term trend reads as "HOLD (pullback in uptrend)" rather than a sell
              signal. Suggested stop-loss/target levels (when shown) are sized off each stock's own ATR (Average
              True Range) — not a fixed percentage.
            </p>
            <p className="text-[10px] text-[#3a4356] mt-3 italic">
              Prices in USD except Samsung Electronics (KRW, Korea Exchange). Cached for 5 minutes — this is a
              swing/long-term watchlist, not a fast-moving intraday signal. Not investment advice — cross-check
              with other sources before trading.
            </p>
          </div>
        </>
      )}
    </div>
  );
}