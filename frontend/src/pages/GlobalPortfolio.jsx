import React, { useState, useEffect, useCallback } from "react";
import { LayoutDashboard, Globe, BrainCircuit, Info, ChevronDown, ChevronRight, Layers, Clock, TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";

const API = "http://localhost:8001";

const BrokerTag = ({ broker }) => {
  const styles = {
    zerodha: "bg-blue-500/10 text-blue-400 border-blue-500/20",
    ibkr: "bg-purple-500/10 text-purple-400 border-purple-500/20",
    etoro: "bg-green-500/10 text-green-400 border-green-500/20",
  };
  const labels = { zerodha: "Kite", ibkr: "IBKR", etoro: "eToro" };
  return (
    <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded border ${styles[broker] || "bg-gray-500/10 text-gray-400 border-gray-500/20"}`}>
      {labels[broker] || broker}
    </span>
  );
};

const getRecommendation = (pnl, qty) => {
  if (!qty) return { text: "No active position", color: "text-slate-400", action: "N/A" };
  if (pnl > 1000) return { text: "Strong profit. Consider trailing stop-loss or booking partial profits.", color: "text-green-400", action: "Take Profit" };
  if (pnl < -1000) return { text: "Significant drawdown. Consider hedging or exiting if thesis is broken.", color: "text-red-400", action: "Hedge/Exit" };
  return { text: "Position within normal volatility range. Hold and monitor key levels.", color: "text-blue-400", action: "Hold" };
};

const groupBySymbol = (positions) => {
  const groups = {};
  positions.forEach(pos => {
    let sym = pos.symbol;
    if (!sym) return;

    // Extract underlying for Nifty/Indian options (e.g., NIFTY26OCT24000CE -> NIFTY)
    if (pos.market === 'India' && (sym.includes('CE') || sym.includes('PE'))) {
      const match = sym.match(/^([A-Z]+)\d+/);
      if (match) sym = match[1];
    }

    if (!groups[sym]) {
      groups[sym] = { symbol: sym, broker: pos.broker, market: pos.market, legs: [], totalPnl: 0, totalValue: 0, totalCost: 0 };
    }
    groups[sym].legs.push(pos);
    groups[sym].totalPnl += pos.unrealized_pnl || 0;
    groups[sym].totalValue += (pos.market_price || 0) * Math.abs(pos.quantity || 0);
    groups[sym].totalCost += (pos.avg_cost || 0) * Math.abs(pos.quantity || 0);
  });
  return Object.values(groups);
};

const PnLBadge = ({ pnl, pct }) => (
  <div className={`flex items-center gap-1 text-xs font-mono font-bold ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
    {pnl >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
    {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}
    {pct !== undefined && <span className="text-[10px] opacity-70">({pct >= 0 ? '+' : ''}{pct.toFixed(1)}%)</span>}
  </div>
);

const OptionGroupCard = ({ group, onSelect, isSelected, usdInr }) => {
  const [expanded, setExpanded] = useState(false);
  const isMultiLeg = group.legs.length > 1;
  const pct = group.totalCost > 0 ? (group.totalPnl / group.totalCost) * 100 : 0;
  const displayValue = group.market === 'India' ? `₹${group.totalValue.toLocaleString(undefined, {maximumFractionDigits: 0})}` : `$${group.totalValue.toFixed(2)}`;

  return (
    <div className={`rounded-2xl border transition-all ${isSelected ? 'bg-blue-500/10 border-blue-500/50 ring-1 ring-blue-500/50' : 'bg-[#111827] border-white/5 hover:border-white/20'}`}>
      <div className="p-4 cursor-pointer group/card" onClick={() => { onSelect(group); if (isMultiLeg) setExpanded(!expanded); }}>
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-3">
            {isMultiLeg && (
              <button onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }} className="text-slate-500 hover:text-white">
                {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              </button>
            )}
            <div className="relative">
              <div className="flex items-center gap-2">
                <span className="font-bold text-white text-lg">{group.symbol}</span>
                <BrokerTag broker={group.broker} />
                {isMultiLeg && (
                  <span className="flex items-center gap-1 text-[10px] bg-orange-500/10 text-orange-400 border border-orange-500/20 px-2 py-0.5 rounded font-bold uppercase">
                    <Layers size={10} /> {group.legs.length} Legs
                  </span>
                )}
              </div>
              <div className="text-[10px] text-white/30 uppercase mt-1">{group.market} Market</div>
            </div>
          </div>
          <div className="text-right flex flex-col items-end gap-2">
            <div>
              <div className="text-white font-mono font-bold text-sm">{displayValue}</div>
              <PnLBadge pnl={group.totalPnl} pct={pct} />
            </div>
            <div className="opacity-0 group-hover/card:opacity-100 transition-opacity">
              <span className="text-[9px] bg-blue-600 text-white px-2 py-0.5 rounded font-bold uppercase">Analyze →</span>
            </div>
          </div>
        </div>
      </div>

      {expanded && isMultiLeg && (
        <div className="border-t border-white/5 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-black/20 text-slate-500 uppercase text-[9px] font-bold">
              <tr>
                <th className="px-4 py-2 text-left">Type</th>
                <th className="px-4 py-2 text-right">Strike</th>
                <th className="px-4 py-2 text-right">Qty</th>
                <th className="px-4 py-2 text-right">Avg Cost</th>
                <th className="px-4 py-2 text-right">LTP</th>
                <th className="px-4 py-2 text-right">Value</th>
                <th className="px-4 py-2 text-right">P&L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {group.legs.map((leg, i) => {
                const legValue = (leg.market_price || 0) * Math.abs(leg.quantity || 0);
                const legCost = (leg.avg_cost || 0) * Math.abs(leg.quantity || 0);
                const legPct = legCost > 0 ? ((leg.unrealized_pnl || 0) / legCost) * 100 : 0;
                const curr = leg.market === 'India' ? '₹' : '$';
                return (
                  <tr key={i} className="hover:bg-white/5">
                    <td className="px-4 py-2">
                      <span className={`font-bold ${leg.contract_type === 'C' ? 'text-blue-400' : leg.contract_type === 'P' ? 'text-orange-400' : 'text-white'}`}>
                        {leg.contract_type === 'C' ? 'CALL' : leg.contract_type === 'P' ? 'PUT' : 'STK'}
                      </span>
                      {leg.quantity < 0 && <span className="ml-1 text-red-400 text-[9px]">SHORT</span>}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-slate-300">{leg.strike || '—'}</td>
                    <td className="px-4 py-2 text-right font-mono text-slate-300">{leg.quantity}</td>
                    <td className="px-4 py-2 text-right font-mono text-slate-300">{curr}{leg.avg_cost?.toFixed(2)}</td>
                    <td className="px-4 py-2 text-right font-mono text-slate-300">{curr}{leg.market_price?.toFixed(2)}</td>
                    <td className="px-4 py-2 text-right font-mono text-slate-300">{curr}{legValue.toFixed(2)}</td>
                    <td className="px-4 py-2 text-right">
                      <PnLBadge pnl={leg.unrealized_pnl || 0} pct={legPct} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

const MarketTimer = ({ market, openHourUTC, closeHourUTC, openMinUTC, closeMinUTC }) => {
  const [timeLeft, setTimeLeft] = useState("");
  const [status, setStatus] = useState("Closed");

  useEffect(() => {
    const update = () => {
      const now = new Date();
      const todayUTC = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
      const open = new Date(todayUTC.getTime() + (openHourUTC * 60 + openMinUTC) * 60000);
      const close = new Date(todayUTC.getTime() + (closeHourUTC * 60 + closeMinUTC) * 60000);
      const fmt = (ms) => {
        const h = Math.floor(ms / 3600000), m = Math.floor((ms % 3600000) / 60000), s = Math.floor((ms % 60000) / 1000);
        return `${h}h ${m}m ${s}s`;
      };
      if (now < open) { setStatus("Opening Soon"); setTimeLeft(fmt(open - now)); }
      else if (now < close) { setStatus("Open"); setTimeLeft(fmt(close - now)); }
      else { setStatus("Closed"); setTimeLeft("Next Session"); }
    };
    const t = setInterval(update, 1000);
    update();
    return () => clearInterval(t);
  }, [openHourUTC, closeHourUTC, openMinUTC, closeMinUTC]);

  return (
    <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border text-[10px] ${status === 'Open' ? 'bg-green-500/10 border-green-500/30' : 'bg-white/5 border-white/10'}`}>
      <Clock size={12} className={status === 'Open' ? 'text-green-400' : 'text-slate-500'} />
      <span className="text-slate-400 font-bold uppercase">{market}</span>
      <span className={`font-mono font-bold ${status === 'Open' ? 'text-green-400' : 'text-slate-400'}`}>{status}</span>
      <span className="text-slate-500">({timeLeft})</span>
    </div>
  );
};

// ── IBKR Account Summary + Open Orders ──────────────────────────────────────

function IBKRSummaryPanel() {
  const [summary, setSummary] = useState(null);
  const [orders, setOrders] = useState([]);
  const [showOrders, setShowOrders] = useState(false);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        const res = await fetch(`${API}/api/ibkr/account-summary`);
        const json = await res.json();
        if (!json.error && json.net_liquidation != null) {
          setSummary(json);
          setVisible(true);
        }
      } catch (e) { /* IBKR not connected — stay invisible */ }
    };
    fetchSummary();
    const interval = setInterval(fetchSummary, 60000);
    return () => clearInterval(interval);
  }, []);

  const fetchOrders = async () => {
    try {
      const res = await fetch(`${API}/api/ibkr/orders`);
      const json = await res.json();
      setOrders(json.orders || []);
    } catch (e) { setOrders([]); }
  };

  const toggleOrders = () => {
    if (!showOrders) fetchOrders();
    setShowOrders(!showOrders);
  };

  if (!visible || !summary) return null;

  const pnlColor = (v) => v >= 0 ? 'text-green-400' : 'text-red-400';

  return (
    <div className="bg-[#111827] border border-white/10 rounded-2xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h3 className="text-sm font-bold text-white flex items-center gap-2">
          <span className="text-[10px] bg-purple-500/10 text-purple-400 border border-purple-500/20 px-2 py-0.5 rounded font-bold uppercase">IBKR</span>
          Account Summary
        </h3>
        <span className="text-[10px] text-slate-500">{summary.currency || 'USD'}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm mb-4">
        <div>
          <div className="text-white/40 text-[10px] uppercase tracking-widest mb-0.5">Net Liquidation</div>
          <div className="text-white font-mono font-bold">${summary.net_liquidation?.toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
        </div>
        <div>
          <div className="text-white/40 text-[10px] uppercase tracking-widest mb-0.5">Buying Power</div>
          <div className="text-white font-mono font-bold">${summary.buying_power?.toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
        </div>
        <div>
          <div className="text-white/40 text-[10px] uppercase tracking-widest mb-0.5">Unrealized P&L</div>
          <div className={`font-mono font-bold ${pnlColor(summary.unrealized_pnl)}`}>
            {summary.unrealized_pnl >= 0 ? '+' : ''}${summary.unrealized_pnl?.toLocaleString(undefined, {minimumFractionDigits: 2})}
          </div>
        </div>
        <div>
          <div className="text-white/40 text-[10px] uppercase tracking-widest mb-0.5">Realized P&L</div>
          <div className={`font-mono font-bold ${pnlColor(summary.realized_pnl)}`}>
            {summary.realized_pnl >= 0 ? '+' : ''}${summary.realized_pnl?.toLocaleString(undefined, {minimumFractionDigits: 2})}
          </div>
        </div>
      </div>
      <button
        onClick={toggleOrders}
        className="text-xs text-purple-400 hover:text-purple-300 underline"
      >
        {showOrders ? 'Hide' : 'Show'} Open Orders
      </button>
      {showOrders && (
        <div className="mt-3 bg-black/30 rounded-xl overflow-x-auto">
          {orders.length === 0 ? (
            <p className="text-xs text-slate-500 p-3">No open orders on IBKR.</p>
          ) : (
            <table className="w-full text-xs">
              <thead className="text-slate-500 uppercase text-[9px] border-b border-white/5">
                <tr>
                  <th className="px-3 py-2 text-left">Symbol</th>
                  <th className="px-3 py-2 text-left">Action</th>
                  <th className="px-3 py-2 text-right">Qty</th>
                  <th className="px-3 py-2 text-right">Type</th>
                  <th className="px-3 py-2 text-right">Limit</th>
                  <th className="px-3 py-2 text-right">Filled</th>
                  <th className="px-3 py-2 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {orders.map((o, i) => (
                  <tr key={i} className="hover:bg-white/5">
                    <td className="px-3 py-2 font-mono font-bold text-white">{o.symbol}</td>
                    <td className={`px-3 py-2 font-bold ${o.action === 'BUY' ? 'text-green-400' : 'text-red-400'}`}>{o.action}</td>
                    <td className="px-3 py-2 text-right font-mono text-slate-300">{o.quantity}</td>
                    <td className="px-3 py-2 text-right text-slate-400">{o.order_type}</td>
                    <td className="px-3 py-2 text-right font-mono text-slate-300">{o.limit_price ? `$${o.limit_price}` : '—'}</td>
                    <td className="px-3 py-2 text-right text-slate-400">{o.filled}/{o.quantity}</td>
                    <td className="px-3 py-2 text-right text-slate-400">{o.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

export default function GlobalPortfolio() {
  const [portfolio, setPortfolio] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('positions');
  const [selectedGroup, setSelectedGroup] = useState(null);
  const [usdInr, setUsdInr] = useState(83.50);
  const [fxSource, setFxSource] = useState('fallback');

  const fetchFxRate = useCallback(async () => {
    try {
      const res = await fetch(`${API}/api/ibkr/fx-rate?base=USD&quote=INR`);
      const data = await res.json();
      if (data.rate) { setUsdInr(data.rate); setFxSource(data.source); }
    } catch (e) { /* use fallback */ }
  }, []);

  const fetchData = useCallback(async () => {
    setError(null);
    try {
      const res = await fetch(`${API}/api/global-portfolio`);
      const data = await res.json();
      if (data.detail || data.error) {
        setError(data.detail || data.error);
      } else {
        setPortfolio(data);
      }
    } catch (e) {
      setError('Could not connect to backend. Make sure the server is running on port 8000.');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    fetchFxRate();
    fetchData();
    const interval = setInterval(fetchData, 30000);
    const fxInterval = setInterval(fetchFxRate, 300000); // refresh FX every 5 min
    return () => { clearInterval(interval); clearInterval(fxInterval); };
  }, [fetchData, fetchFxRate]);

  const rawAssets = activeTab === 'positions' ? (portfolio?.positions || []) : (portfolio?.holdings || []);
  const groups = groupBySymbol(rawAssets);

  // Global wealth: sum all positions + holdings, convert INR to USD
  const globalWealth = (() => {
    let totalUSD = 0;
    const all = [...(portfolio?.positions || []), ...(portfolio?.holdings || [])];
    all.forEach(a => {
      const val = (a.market_price || 0) * Math.abs(a.quantity || 0);
      totalUSD += a.market === 'India' ? val / usdInr : val;
    });
    return { usd: totalUSD, inr: totalUSD * usdInr };
  })();

  // Compute total P&L in USD — the backend's summary.total_unrealized_pnl is a raw
  // sum of INR (Zerodha) + USD (IBKR) P&L without currency conversion, so it's
  // meaningless as a single number. We recompute it here using the live FX rate.
  const totalPnlUSD = (() => {
    const all = [...(portfolio?.positions || []), ...(portfolio?.holdings || [])];
    return all.reduce((sum, a) => {
      const pnl = a.unrealized_pnl || 0;
      return sum + (a.market === 'India' ? pnl / usdInr : pnl);
    }, 0);
  })();
  const pnlPct = globalWealth.usd > 0 ? (totalPnlUSD / Math.max(globalWealth.usd - totalPnlUSD, 1)) * 100 : 0;

  const selectedRec = selectedGroup ? getRecommendation(
    selectedGroup.totalPnl,
    selectedGroup.legs.reduce((s, l) => s + Math.abs(l.quantity || 0), 0)
  ) : null;

  return (
    <div className="min-h-screen bg-[#0a0e1a] text-white p-6 max-w-7xl mx-auto">
      {/* Error banner */}
      {error && (
        <div className="mb-6 bg-red-500/10 border border-red-500/30 rounded-2xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-red-400 font-semibold text-sm">Failed to load portfolio data</p>
            <p className="text-slate-400 text-xs mt-1">{error}</p>
            <p className="text-slate-500 text-xs mt-1">Connect Zerodha and/or IBKR in Settings to see live positions.</p>
          </div>
        </div>
      )}

      {/* Market Status Bar */}
      <div className="flex gap-3 mb-6 flex-wrap">
        {/* NSE: 9:15 AM - 3:30 PM IST = 3:45 UTC - 10:00 UTC */}
        <MarketTimer market="NSE 🇮🇳" openHourUTC={3} openMinUTC={45} closeHourUTC={10} closeMinUTC={0} />
        {/* NYSE: 9:30 AM - 4:00 PM EST = 14:30 UTC - 21:00 UTC */}
        <MarketTimer market="NYSE 🇺🇸" openHourUTC={14} openMinUTC={30} closeHourUTC={21} closeMinUTC={0} />
        <div className="flex items-center gap-2 px-3 py-1.5 bg-white/5 rounded-full border border-white/10 text-[10px]">
          <span className="text-slate-400 font-bold">USD/INR:</span>
          <span className="font-mono text-yellow-400 font-bold">₹{usdInr.toFixed(2)}</span>
          <span className={`text-[9px] ${fxSource === 'ibkr_live' ? 'text-green-400' : 'text-slate-500'}`}>
            {fxSource === 'ibkr_live' ? '● LIVE' : '● EST'}
          </span>
        </div>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-blue-500/10 rounded-2xl text-blue-500"><Globe size={28} /></div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Global Command Center</h1>
            <p className="text-white/40 text-sm">Unified Wealth & Risk Analysis</p>
          </div>
        </div>
        <button onClick={fetchData} className="px-5 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-full text-sm font-medium transition-all">
          Refresh
        </button>
      </div>

      {/* Summary Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="bg-[#111827] p-5 rounded-2xl border border-white/5">
          <div className="text-white/40 text-[10px] uppercase tracking-widest mb-1">Total Portfolio Value</div>
          <div className="text-2xl font-mono font-bold text-white">${globalWealth.usd.toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
          <div className="text-[10px] text-slate-500 font-mono mt-1">≈ ₹{globalWealth.inr.toLocaleString(undefined, {maximumFractionDigits: 0})}</div>
        </div>
        <div className="bg-[#111827] p-5 rounded-2xl border border-white/5">
          <div className="text-white/40 text-[10px] uppercase tracking-widest mb-1">Total Unrealized P&L</div>
          <div className={`text-2xl font-mono font-bold ${totalPnlUSD >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {totalPnlUSD >= 0 ? '+' : ''}${totalPnlUSD.toLocaleString(undefined, {minimumFractionDigits: 2})}
          </div>
          <div className={`text-[10px] font-mono mt-1 ${pnlPct >= 0 ? 'text-green-400/70' : 'text-red-400/70'}`}>
            {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}% overall
          </div>
        </div>
        <div className="bg-[#111827] p-5 rounded-2xl border border-white/5">
          <div className="text-white/40 text-[10px] uppercase tracking-widest mb-1">Total Assets</div>
          <div className="text-2xl font-mono font-bold text-white">{portfolio?.summary?.total_assets || 0}</div>
          <div className="text-[10px] text-slate-500 mt-1">Across all brokers</div>
        </div>
        <div className="bg-[#111827] p-5 rounded-2xl border border-white/5">
          <div className="text-white/40 text-[10px] uppercase tracking-widest mb-1">Market Exposure</div>
          <div className="flex gap-4 mt-2">
            <div>
              <div className="text-blue-400 font-bold text-lg">{portfolio?.summary?.market_split?.India || 0}</div>
              <div className="text-[10px] text-slate-500">🇮🇳 India</div>
            </div>
            <div>
              <div className="text-purple-400 font-bold text-lg">{portfolio?.summary?.market_split?.US || 0}</div>
              <div className="text-[10px] text-slate-500">🇺🇸 US</div>
            </div>
          </div>
        </div>
      </div>

      {/* IBKR Account Summary — shown when IBKR is connected */}
      <IBKRSummaryPanel />

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-4">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xl font-bold">Portfolio Assets</h2>
              <div className="flex bg-black/40 p-1 rounded-xl border border-white/5">
                <button onClick={() => { setActiveTab('positions'); setSelectedGroup(null); }} className={`px-4 py-1.5 text-xs rounded-lg transition-all ${activeTab === 'positions' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white'}`}>
                  Positions
                </button>
                <button onClick={() => { setActiveTab('holdings'); setSelectedGroup(null); }} className={`px-4 py-1.5 text-xs rounded-lg transition-all ${activeTab === 'holdings' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white'}`}>
                  Holdings
                </button>
              </div>
            </div>

            <div className="space-y-3">
              {groups.length === 0 ? (
                <div className="bg-[#111827] rounded-3xl p-12 text-center border border-dashed border-white/10">
                  <div className="text-4xl mb-4">🍃</div>
                  <div className="text-white/40 text-lg">No {activeTab} found in connected accounts</div>
                </div>
              ) : (
                groups.map((group, i) => (
                  <OptionGroupCard key={i} group={group} onSelect={setSelectedGroup} isSelected={selectedGroup?.symbol === group.symbol} usdInr={usdInr} />
                ))
              )}
            </div>
          </div>

          {/* Analysis Panel */}
          <div className="lg:col-span-1">
            <div className="bg-[#111827] rounded-3xl border border-white/10 p-6 sticky top-24">
              <div className="flex items-center gap-3 mb-6">
                <div className="p-2 bg-blue-500/10 rounded-lg text-blue-500"><BrainCircuit size={24} /></div>
                <h2 className="text-xl font-bold text-white">Combined Analysis</h2>
              </div>

              {selectedGroup ? (
                <div className="space-y-5">
                  <div className="flex justify-between items-start">
                    <div>
                      <h3 className="text-2xl font-bold text-white">{selectedGroup.symbol}</h3>
                      <p className="text-white/40 text-sm">{selectedGroup.legs.length} leg{selectedGroup.legs.length > 1 ? 's' : ''} · {selectedGroup.broker}</p>
                    </div>
                    <div className="text-right">
                      <div className="text-[10px] text-white/30 uppercase font-bold">Total Value</div>
                      <div className="text-lg font-mono font-bold text-white">
                        {selectedGroup.market === 'India' ? '₹' : '$'}{selectedGroup.totalValue.toFixed(2)}
                      </div>
                      <PnLBadge pnl={selectedGroup.totalPnl} pct={selectedGroup.totalCost > 0 ? (selectedGroup.totalPnl / selectedGroup.totalCost) * 100 : 0} />
                    </div>
                  </div>

                  <div className="space-y-2">
                    {selectedGroup.legs.map((leg, i) => {
                      const legCost = (leg.avg_cost || 0) * Math.abs(leg.quantity || 0);
                      const legPct = legCost > 0 ? ((leg.unrealized_pnl || 0) / legCost) * 100 : 0;
                      return (
                        <div key={i} className="flex justify-between items-center p-3 bg-white/5 rounded-xl border border-white/5">
                          <div>
                            <span className={`text-xs font-bold ${leg.contract_type === 'C' ? 'text-blue-400' : leg.contract_type === 'P' ? 'text-orange-400' : 'text-white'}`}>
                              {leg.contract_type === 'C' ? 'CALL' : leg.contract_type === 'P' ? 'PUT' : 'STOCK'}
                            </span>
                            {leg.strike && <span className="text-white/40 text-xs ml-2">@ {leg.strike}</span>}
                          </div>
                          <PnLBadge pnl={leg.unrealized_pnl || 0} pct={legPct} />
                        </div>
                      );
                    })}
                  </div>

                  <div className="p-4 bg-black/40 rounded-2xl border border-white/5 space-y-3">
                    <div className="flex items-center gap-2 text-xs font-bold text-blue-400 uppercase tracking-wider">
                      <Info size={14} /> AI Recommendation
                    </div>
                    <p className={`text-sm leading-relaxed font-medium ${selectedRec?.color}`}>{selectedRec?.text}</p>
                    <button className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs rounded-lg font-bold transition-all">
                      {selectedRec?.action}
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="p-3 bg-white/5 rounded-xl border border-white/5">
                      <div className="text-[10px] text-white/30 uppercase font-bold mb-1">Total Legs</div>
                      <div className="text-white font-mono">{selectedGroup.legs.length}</div>
                    </div>
                    <div className="p-3 bg-white/5 rounded-xl border border-white/5">
                      <div className="text-[10px] text-white/30 uppercase font-bold mb-1">Net Qty</div>
                      <div className="text-white font-mono">{selectedGroup.legs.reduce((s, l) => s + (l.quantity || 0), 0)}</div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-64 text-center">
                  <div className="p-4 bg-white/5 rounded-full text-white/20 mb-4"><LayoutDashboard size={40} /></div>
                  <p className="text-white/40 text-sm max-w-xs">Select an asset to view combined analysis and AI-driven recommendations</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}