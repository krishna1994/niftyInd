import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend } from 'recharts';
import { Plus, Trash2, Play, Info, AlertTriangle, Search, Zap, RefreshCw, TrendingUp, Calendar, Hash } from 'lucide-react';
import axios from 'axios';

const API = 'http://localhost:8001';

// QCOM Stochastic K > 80 Alert Banner
const QCOMAlert = ({ symbol }) => {
  const [alert, setAlert] = useState(null);

  useEffect(() => {
    if (symbol !== 'QCOM') { setAlert(null); return; }
    const check = async () => {
      try {
        const res = await axios.get(`${API}/api/watchlist`);
        const qcom = res.data?.results?.find(r => r.symbol === 'QCOM');
        if (qcom?.indicators?.stoch_k > 80) {
          setAlert({ stoch_k: qcom.indicators.stoch_k });
        } else {
          setAlert(null);
        }
      } catch (e) { /* silent */ }
    };
    check();
    const interval = setInterval(check, 60000);
    return () => clearInterval(interval);
  }, [symbol]);

  if (!alert) return null;

  return (
    <div className="flex items-center gap-3 p-3 bg-red-900/30 border border-red-500/50 rounded-lg text-red-200 text-xs font-medium animate-pulse mb-4">
      <AlertTriangle size={16} className="text-red-400 shrink-0" />
      <div>
        <span className="font-bold text-red-400">⚠️ QCOM RISK:</span> Stochastic K = {alert.stoch_k?.toFixed(1)} (Overbought). 
        Backtests show high failure rate for Monday ICs in this regime.
      </div>
    </div>
  );
};

// Professional Symbol Search
const SymbolSearch = ({ value, onChange }) => {
  const [query, setQuery] = useState(value);
  const [suggestions, setSuggestions] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [livePrice, setLivePrice] = useState(null);

  const fetchSuggestions = useCallback(async (q) => {
    if (q.length < 2) { setSuggestions([]); return; }
    try {
      const res = await axios.get(`${API}/api/watchlist/suggest?q=${q}`);
      setSuggestions(res.data?.suggestions || []);
    } catch (e) { setSuggestions([]); }
  }, []);

  const fetchPrice = useCallback(async (sym) => {
    try {
      const res = await axios.get(`${API}/api/ibkr/contract-details?symbol=${sym}&strike=0&expiry=&option_type=`);
      setLivePrice(res.data.ltp);
    } catch (e) { setLivePrice(null); }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => fetchSuggestions(query), 300);
    return () => clearTimeout(timer);
  }, [query, fetchSuggestions]);

  const handleSelect = (sym) => {
    setQuery(sym);
    onChange(sym);
    setShowDropdown(false);
    fetchPrice(sym);
  };

  return (
    <div className="relative">
      <div className="flex items-center gap-2 bg-[#1a1f35] border border-white/10 rounded-md px-3 py-1.5 transition-all focus-within:border-blue-500">
        <Search size={14} className="text-slate-500" />
        <input
          value={query}
          onChange={(e) => { setQuery(e.target.value.toUpperCase()); setShowDropdown(true); }}
          onFocus={() => setShowDropdown(true)}
          onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
          placeholder="Search Symbol..."
          className="bg-transparent text-white focus:outline-none text-sm w-32 font-medium"
        />
        {livePrice && (
          <span className="text-green-400 text-xs font-mono ml-2 border-l border-white/10 pl-2">
            ${livePrice.toFixed(2)}
          </span>
        )}
      </div>
      {showDropdown && suggestions.length > 0 && (
        <div className="absolute top-full left-0 mt-1 w-64 bg-[#111827] border border-white/10 rounded-md shadow-2xl z-50 py-1 max-h-48 overflow-y-auto">
          {suggestions.map((s, i) => (
            <button
              key={i}
              onMouseDown={() => handleSelect(s.symbol || s)}
              className="w-full text-left px-4 py-2 text-sm text-slate-300 hover:bg-blue-600 hover:text-white transition-colors"
            >
              <span className="font-bold">{s.symbol || s}</span>
              {s.name && <span className="text-slate-500 ml-2 text-xs">{s.name}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const IBKROptionStrategy = () => {
  const [symbol, setSymbol] = useState('QCOM');
  const [spotPrice, setSpotPrice] = useState(0);
  const [legs, setLegs] = useState([]);
  const [executionStatus, setExecutionStatus] = useState(null);
  const [liveRefreshing, setLiveRefreshing] = useState(false);
  
  // New state for real IBKR data
  const [availableExpiries, setAvailableExpiries] = useState([]);
  const [availableStrikes, setAvailableStrikes] = useState([]);
  const [loadingStrikes, setLoadingStrikes] = useState(false);

  // Helper to find closest actual strike
  const findClosestStrike = (target, strikes) => {
    if (!strikes || strikes.length === 0) return target;
    return strikes.reduce((prev, curr) => 
      Math.abs(curr - target) < Math.abs(prev - target) ? curr : prev
    );
  };

  // Update spot and fetch real strikes when symbol changes
  useEffect(() => {
    const updateSymbolData = async () => {
      setLoadingStrikes(true);
      try {
        // 1. Get Spot Price
        const spotRes = await axios.get(`${API}/api/ibkr/contract-details?symbol=${symbol}&strike=0&expiry=&option_type=`);
        const newSpot = spotRes.data.ltp || 100;
        setSpotPrice(newSpot);
        
        // 2. Get Actual Tradable Strikes and Expiries
        const strikesRes = await axios.get(`${API}/api/ibkr/strikes?symbol=${symbol}`);
        if (strikesRes.data.success) {
          const { expiries, strikes } = strikesRes.data;
          setAvailableExpiries(expiries);
          setAvailableStrikes(strikes);
          
          // Default to nearest expiry
          const defaultExpiry = expiries[0];
          
          // 3. Reset legs to a default Iron Condor using ACTUAL strikes
          const callStrike = findClosestStrike(newSpot * 1.1, strikes);
          const putStrike = findClosestStrike(newSpot * 0.9, strikes);
          
          setLegs([
            { id: 1, type: 'SELL', optionType: 'C', strike: callStrike, quantity: 1, expiry: defaultExpiry, ltp: null, oi: null, volume: null },
            { id: 2, type: 'SELL', optionType: 'P', strike: putStrike, quantity: 1, expiry: defaultExpiry, ltp: null, oi: null, volume: null },
          ]);
        }
      } catch (e) {
        console.error("Error updating symbol data:", e);
      } finally {
        setLoadingStrikes(false);
      }
    };
    
    if (symbol) {
      updateSymbolData();
    }
  }, [symbol]);

  const refreshLiveData = useCallback(async () => {
    setLiveRefreshing(true);
    const updated = await Promise.all(legs.map(async (leg) => {
      try {
        const res = await axios.get(`${API}/api/ibkr/contract-details?symbol=${symbol}&strike=${leg.strike}&expiry=${leg.expiry}&option_type=${leg.optionType}`);
        return { ...leg, ltp: res.data.ltp, oi: res.data.oi, volume: res.data.volume };
      } catch (e) { return leg; }
    }));
    setLegs(updated);
    setLiveRefreshing(false);
  }, [legs, symbol]);

  useEffect(() => {
    const interval = setInterval(refreshLiveData, 30000);
    return () => clearInterval(interval);
  }, [refreshLiveData]);

  const payoffData = useMemo(() => {
    const data = [];
    const startPrice = spotPrice * 0.8;
    const endPrice = spotPrice * 1.2;
    const step = (endPrice - startPrice) / 100;

    for (let i = 0; i <= 100; i++) {
      const price = startPrice + i * step;
      let totalPnL = 0;
      legs.forEach(leg => {
        let legPnL = 0;
        if (leg.optionType === 'C') {
          const payoff = Math.max(0, price - leg.strike);
          legPnL = leg.type === 'BUY' ? payoff : -payoff;
        } else {
          const payoff = Math.max(0, leg.strike - price);
          legPnL = leg.type === 'BUY' ? payoff : -payoff;
        }
        totalPnL += legPnL * leg.quantity * 100;
      });
      data.push({ price: price.toFixed(2), pnl: totalPnL });
    }
    return data;
  }, [legs, spotPrice]);

  const strategySummary = useMemo(() => {
    let totalPremium = 0;
    let maxProfit = 0;
    let maxLoss = 0;

    legs.forEach(leg => {
      const premium = leg.ltp || 0;
      const cost = leg.type === 'BUY' ? premium : -premium;
      totalPremium += cost * leg.quantity * 100;
    });

    maxProfit = -totalPremium; 
    maxLoss = (legs[0]?.strike - legs[1]?.strike || 0) * 100 - totalPremium;

    return { totalPremium, maxProfit, maxLoss };
  }, [legs]);

  const addLeg = () => {
    const newId = legs.length > 0 ? Math.max(...legs.map(l => l.id)) + 1 : 1;
    setLegs([...legs, { 
      id: newId, 
      type: 'BUY', 
      optionType: 'C', 
      strike: availableStrikes[0] || spotPrice, 
      quantity: 1, 
      expiry: availableExpiries[0] || '2026-10-23', 
      ltp: null, oi: null, volume: null 
    }]);
  };

  const removeLeg = (id) => setLegs(legs.filter(l => l.id !== id));
  const updateLeg = (id, field, value) => setLegs(legs.map(l => l.id === id ? { ...l, [field]: value } : l));

  const executeStrategy = async () => {
    setExecutionStatus('executing');
    try {
      await axios.post(`${API}/api/brokers/order`, {
        broker_name: 'ibkr',
        order_details: { strategy: legs, symbol }
      });
      setExecutionStatus('success');
    } catch (e) {
      setExecutionStatus('error');
    }
  };

  return (
    <div className="p-6 bg-[#0a0e1a] min-h-screen text-slate-200 font-sans">
      {/* Top Navigation Bar */}
      <div className="flex justify-between items-center mb-6 bg-[#111827] p-4 rounded-xl border border-white/5 shadow-lg">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-600 rounded-lg text-white">
              <TrendingUp size={20} />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white leading-none">Strategy Builder</h1>
              <p className="text-xs text-slate-500 mt-1">Professional Option Architect</p>
            </div>
          </div>
          <div className="h-8 w-px bg-white/10" />
          <SymbolSearch value={symbol} onChange={setSymbol} />
        </div>
        
        <div className="flex items-center gap-4">
          <div className="flex flex-col items-end">
            <span className="text-[10px] text-slate-500 uppercase font-bold">Live Spot</span>
            <div className="flex items-center gap-2">
              <span className="text-lg font-mono font-bold text-white">${spotPrice.toFixed(2)}</span>
              <button 
                onClick={refreshLiveData}
                className={`p-1 rounded-md transition-all ${liveRefreshing ? 'bg-blue-500 text-white animate-spin' : 'bg-slate-800 text-slate-400 hover:text-white'}`}
              >
                <RefreshCw size={14} />
              </button>
            </div>
          </div>
        </div>
      </div>

      <QCOMAlert symbol={symbol} />

      <div className="grid grid-cols-12 gap-6">
        {/* Left: Leg Table */}
        <div className="col-span-12 lg:col-span-8 space-y-6">
          <div className="bg-[#111827] rounded-xl border border-white/10 overflow-hidden shadow-xl">
            <div className="p-4 border-b border-white/5 bg-white/5 flex justify-between items-center">
              <div className="flex items-center gap-3">
                <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">Strategy Legs</h2>
                {loadingStrikes && <div className="animate-spin rounded-full h-3 w-3 border-2 border-blue-500 border-t-transparent" />}
              </div>
              <button onClick={addLeg} className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-md text-xs font-bold transition-all">
                <Plus size={14} /> Add Leg
              </button>
            </div>
            
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-black/20 text-slate-500 uppercase text-[10px] font-bold">
                  <tr>
                    <th className="px-4 py-3">Action</th>
                    <th className="px-4 py-3">Type</th>
                    <th className="px-4 py-3">Strike</th>
                    <th className="px-4 py-3">Expiry</th>
                    <th className="px-4 py-3">Qty</th>
                    <th className="px-4 py-3">LTP</th>
                    <th className="px-4 py-3">OI</th>
                    <th className="px-4 py-3">Vol</th>
                    <th className="px-4 py-3"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {legs.map((leg) => (
                    <tr key={leg.id} className="hover:bg-white/5 transition-colors group">
                      <td className="px-4 py-3">
                        <select 
                          value={leg.type} 
                          onChange={(e) => updateLeg(leg.id, 'type', e.target.value)}
                          className={`rounded px-2 py-1 text-xs font-bold outline-none ${leg.type === 'BUY' ? 'bg-green-500/20 text-green-400 border border-green-500/30' : 'bg-red-500/20 text-red-400 border border-red-500/30'}`}
                        >
                          <option value="BUY">BUY</option>
                          <option value="SELL">SELL</option>
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <select 
                          value={leg.optionType} 
                          onChange={(e) => updateLeg(leg.id, 'optionType', e.target.value)}
                          className="bg-transparent text-white outline-none text-xs"
                        >
                          <option value="C">Call</option>
                          <option value="P">Put</option>
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <Hash size={12} className="text-slate-600" />
                          <select 
                            value={leg.strike} 
                            onChange={(e) => updateLeg(leg.id, 'strike', parseFloat(e.target.value))}
                            className="bg-transparent text-white outline-none font-mono text-xs"
                          >
                            {availableStrikes.map(s => <option key={s} value={s}>{s}</option>)}
                            {availableStrikes.length === 0 && <option value={leg.strike}>{leg.strike}</option>}
                          </select>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <Calendar size={12} className="text-slate-600" />
                          <select 
                            value={leg.expiry} 
                            onChange={(e) => updateLeg(leg.id, 'expiry', e.target.value)}
                            className="bg-transparent text-slate-400 outline-none text-xs"
                          >
                            {availableExpiries.map(e => <option key={e} value={e}>{e}</option>)}
                            {availableExpiries.length === 0 && <option value={leg.expiry}>{leg.expiry}</option>}
                          </select>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <input 
                          type="number" 
                          value={leg.quantity} 
                          onChange={(e) => updateLeg(leg.id, 'quantity', parseInt(e.target.value))}
                          className="bg-transparent text-white outline-none font-mono text-xs w-12"
                        />
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-green-400">${leg.ltp?.toFixed(2) || '0.00'}</td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-400">{leg.oi?.toLocaleString() || '0'}</td>
                      <td className="px-4 py-3 font-mono text-xs text-slate-400">{leg.volume?.toLocaleString() || '0'}</td>
                      <td className="px-4 py-3 text-right">
                        <button onClick={() => removeLeg(leg.id)} className="text-slate-600 hover:text-red-400 transition-colors">
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Payoff Chart */}
          <div className="bg-[#111827] p-6 rounded-xl border border-white/10 shadow-xl">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400">Payoff Analysis</h2>
              <div className="flex gap-4 text-xs">
                <div className="flex items-center gap-1 text-slate-400">
                  <div className="w-3 h-0.5 bg-blue-500" /> P&L Curve
                </div>
                <div className="flex items-center gap-1 text-slate-400">
                  <div className="w-3 h-0.5 bg-orange-500" /> Current Spot
                </div>
              </div>
            </div>
            <div className="h-[350px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={payoffData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="price" stroke="#475569" tick={{ fontSize: 11 }} label={{ value: 'Spot Price', position: 'insideBottom', offset: -5, fill: '#475569', fontSize: 10 }} />
                  <YAxis stroke="#475569" tick={{ fontSize: 11 }} label={{ value: 'PnL ($)', angle: -90, position: 'insideLeft', fill: '#475569', fontSize: 10 }} />
                  <Tooltip 
                    contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', color: '#f1f5f9' }}
                    itemStyle={{ color: '#3b82f6' }}
                  />
                  <ReferenceLine y={0} stroke="#ef4444" strokeWidth={1} />
                  <ReferenceLine x={spotPrice.toFixed(2)} stroke="#f59e0b" strokeDasharray="5 5" label={{ value: 'Spot', position: 'top', fill: '#f59e0b', fontSize: 10 }} />
                  <Line type="monotone" dataKey="pnl" stroke="#3b82f6" strokeWidth={3} dot={false} animationDuration={300} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Right: Order Summary & Execution */}
        <div className="col-span-12 lg:col-span-4 space-y-6">
          <div className="bg-[#111827] p-6 rounded-xl border border-white/10 shadow-xl sticky top-24">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-6">Order Summary</h2>
            
            <div className="space-y-4 mb-8">
              <div className="flex justify-between items-center py-3 border-b border-white/5">
                <span className="text-slate-400 text-sm">Net Premium</span>
                <span className={`font-mono font-bold ${strategySummary.totalPremium >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  ${strategySummary.totalPremium.toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between items-center py-3 border-b border-white/5">
                <span className="text-slate-400 text-sm">Max Profit</span>
                <span className="font-mono font-bold text-green-400">${strategySummary.maxProfit.toFixed(2)}</span>
              </div>
              <div className="flex justify-between items-center py-3 border-b border-white/5">
                <span className="text-slate-400 text-sm">Max Risk</span>
                <span className="font-mono font-bold text-red-400">${strategySummary.maxLoss.toFixed(2)}</span>
              </div>
            </div>

            <button 
              onClick={executeStrategy}
              disabled={executionStatus === 'executing'}
              className={`w-full py-4 rounded-xl font-bold flex items-center justify-center gap-2 transition-all shadow-lg ${
                executionStatus === 'success' ? 'bg-green-600 text-white' : 
                executionStatus === 'error' ? 'bg-red-600 text-white' : 'bg-blue-600 hover:bg-blue-500 text-white'
              }`}
            >
              <Play size={18} />
              {executionStatus === 'executing' ? 'Executing...' : 
               executionStatus === 'success' ? 'Executed!' : 
               executionStatus === 'error' ? 'Failed' : 'Execute Strategy'}
            </button>

            <div className="mt-6 p-4 bg-black/40 rounded-lg border border-white/5 flex items-start gap-3">
              <Info size={16} className="text-blue-400 shrink-0 mt-0.5" />
              <p className="text-[11px] text-slate-500 leading-relaxed">
                Orders are routed as separate market orders to IBKR. Ensure your TWS is open and API is enabled.
              </p>
            </div>
          </div>

          {/* Liquidity Chart */}
          <div className="bg-[#111827] p-6 rounded-xl border border-white/10 shadow-xl">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-4">Leg Liquidity</h2>
            <div className="h-[200px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={legs.map(l => ({ name: `${l.strike}${l.optionType}`, oi: l.oi || 0, vol: l.volume || 0 }))}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="name" stroke="#475569" tick={{ fontSize: 10 }} />
                  <YAxis stroke="#475569" tick={{ fontSize: 10 }} />
                  <Tooltip contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#f1f5f9' }} />
                  <Bar dataKey="oi" name="OI" fill="#3b82f6" radius={[2, 2, 0, 0]} />
                  <Bar dataKey="vol" name="Vol" fill="#8b5cf6" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default IBKROptionStrategy;