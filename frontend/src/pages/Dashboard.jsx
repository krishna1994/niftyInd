import React, { useState, useEffect, useCallback } from 'react';
import { AlertTriangle, Info, Clock, Layers, ShieldAlert, Activity, Zap } from 'lucide-react';
import SignalCard from '../components/dashboard/SignalCard';
import IndicatorBoard from '../components/dashboard/IndicatorBoard';
import StrikeCard from '../components/dashboard/StrikeCard';
import VixWarning from '../components/dashboard/VixWarning';
import MarketContext from '../components/dashboard/MarketContext';
import VolatilityCard from '../components/dashboard/VolatilityCard';

const API_BASE = 'http://localhost:8001';

// ── Signal Divergence Explainer ─────────────────────────────────────────────
// These two signals are DELIBERATELY independent systems answering
// DIFFERENT questions, and can legitimately disagree:
//   - Main Signal (this page, /api/signal): a multi-day SWING signal for
//     WEEKLY OPTIONS, driven by MACD + Supertrend + Candle Pattern on the
//     DAILY chart (empirically weighted from a 1-year backtest — see
//     backend/signal_engine.py). STAY OUT means neither bull nor bear score
//     crossed the 60% confidence threshold — it does NOT mean "bearish".
//   - CAS Signal (/cas-signal tab, /api/cas-signal): a SEPARATE ML model
//     forecasting ONLY the few-minutes-long NSE Closing Auction Session
//     (CAS) window, using cross-asset features (Bank Nifty, USD/INR, Dow
//     futures overnight, PCR, futures basis) — a completely different time
//     horizon and completely different inputs.
// This component fetches the live CAS signal and, whenever it disagrees
// with the main signal shown on this page, explains WHY in plain English
// using the actual live numbers from both systems (not a generic canned
// message) so the discrepancy is never a mystery.

function SignalComparisonCard({ mainSignal }) {
  const [cas, setCas] = useState(null);

  const fetchCas = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/cas-signal`);
      const json = await res.json();
      if (json.success !== false) setCas(json);
    } catch (e) {
      setCas(null);
    }
  }, []);

  useEffect(() => {
    fetchCas();
    const interval = setInterval(fetchCas, 30000);
    return () => clearInterval(interval);
  }, [fetchCas]);

  if (!cas || !mainSignal) return null;

  // Map both signals onto a common BULLISH/BEARISH/NEUTRAL axis for comparison
  const mainDirection = mainSignal.direction; // BULLISH | BEARISH | NEUTRAL
  const casDirection = cas.directional_bias;  // BULLISH | BEARISH | UNKNOWN

  const disagree = mainDirection !== 'NEUTRAL' && casDirection && casDirection !== 'UNKNOWN' && mainDirection !== casDirection;
  const mainIsNeutral = mainDirection === 'NEUTRAL';

  if (!disagree && !mainIsNeutral) return null; // fully agree and decisive — nothing to explain

  return (
    <div className="bg-[#0f1629] border-2 border-[#ffa502]/30 rounded-lg p-5">
      <h3 className="text-sm font-bold text-[#e8eaf6] mb-3 flex items-center gap-2">
        <Info className="w-4 h-4 text-[#ffa502]" />
        Why Main Signal and CAS Signal Show Different Views
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
        <div className="bg-[#0a0e1a] border border-[#1a2035] rounded p-3">
          <p className="text-[10px] text-[#546e7a] uppercase flex items-center gap-1">
            <Layers className="w-3 h-3" /> Main Signal (this page)
          </p>
          <p className="text-lg font-mono font-bold" style={{ color: mainSignal.signal === 'BUY CE' ? '#00d4aa' : mainSignal.signal === 'BUY PE' ? '#ff4757' : '#ffa502' }}>
            {mainSignal.signal}
          </p>
          <p className="text-[11px] text-[#8892a6] mt-1">
            Bull {mainSignal.bull_confidence?.toFixed(1)}% vs Bear {mainSignal.bear_confidence?.toFixed(1)}%
            {mainIsNeutral && ' — neither crossed the 60% threshold, so it stays neutral rather than forcing a call.'}
          </p>
        </div>
        <div className="bg-[#0a0e1a] border border-[#1a2035] rounded p-3">
          <p className="text-[10px] text-[#546e7a] uppercase flex items-center gap-1">
            <Clock className="w-3 h-3" /> CAS Signal (closing-window)
          </p>
          <p className="text-lg font-mono font-bold" style={{ color: casDirection === 'BULLISH' ? '#00d4aa' : casDirection === 'BEARISH' ? '#ff4757' : '#546e7a' }}>
            {casDirection}
          </p>
          <p className="text-[11px] text-[#8892a6] mt-1">
            {Math.round((cas.directional_confidence || 0) * 100)}% model confidence, {Math.round((cas.directional_pop || 0) * 100)}% POP
          </p>
        </div>
      </div>

      <p className="text-xs text-[#e8eaf6] leading-relaxed bg-[#ffa502]/5 border border-[#ffa502]/20 rounded p-3 mb-3">
        These are two <span className="font-bold text-[#ffa502]">deliberately independent</span> systems answering
        different questions — they are allowed to disagree, and it's not a bug:
      </p>

      <ul className="space-y-1.5 text-[11px] text-[#8892a6] mb-3">
        <li>
          • <span className="text-[#e8eaf6] font-semibold">Main Signal</span> is a multi-day swing view for weekly
          options based on the DAILY chart's MACD + Supertrend + Candle Pattern (the only 3 indicators with real
          predictive weight, per a 1-year backtest). Right now: {mainSignal.indicators?.macd?.label?.toLowerCase()},
          while {mainSignal.indicators?.supertrend?.label?.toLowerCase()} — they're pulling in opposite directions,
          which is exactly why the confidence is tied and the signal stays neutral rather than guessing.
        </li>
        <li>
          • <span className="text-[#e8eaf6] font-semibold">CAS Signal</span> forecasts ONLY the few-minutes-long NSE
          Closing Auction Session using a completely different ML model trained on cross-asset data (Bank Nifty,
          USD/INR, overnight Dow futures, PCR, futures basis) — a much shorter, more specific time horizon than the
          daily-chart swing view.
        </li>
      </ul>

      <p className="text-[10px] text-[#546e7a] italic">
        Treat them as two separate opinions from two separate models covering two separate timeframes — cross-check
        both (and the options chain analysis) rather than expecting them to always match. See the CAS Signal tab
        for the full live reasoning behind its current call.
      </p>
    </div>
  );
}

export default function Dashboard({ signalData, loading }) {
  const [expandedIndicator, setExpandedIndicator] = useState(null);
  const [portfolioGreeks, setPortfolioGreeks] = useState(null);

  useEffect(() => {
    const fetchGreeks = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/positions/live`);
        const data = await res.json();
        if (data.portfolio_greeks) {
          setPortfolioGreeks(data.portfolio_greeks);
        }
      } catch (e) {
        console.error("Failed to fetch portfolio greeks", e);
      }
    };

    fetchGreeks();
    const interval = setInterval(fetchGreeks, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-32 bg-[#0f1629] rounded"></div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="h-64 bg-[#0f1629] rounded"></div>
          <div className="h-64 bg-[#0f1629] rounded"></div>
          <div className="h-64 bg-[#0f1629] rounded"></div>
        </div>
      </div>
    );
  }

  if (!signalData) {
    return (
      <div className="text-center py-12 text-[#546e7a]">
        <AlertTriangle className="w-12 h-12 mx-auto mb-4" />
        <p>Unable to fetch signal data. Check backend connection.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* LEFT COLUMN: Market Intelligence (3 cols) */}
      <div className="lg:col-span-3 space-y-6">
        <VolatilityCard />
        
        {signalData.vix_warning && (
          <VixWarning
            vix={signalData.vix}
            regime={signalData.vix_regime}
            penalty={signalData.vix_penalty}
            message={signalData.vix_warning_message}
          />
        )}

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center space-x-2 mb-4 text-slate-200 font-bold text-sm">
                <Activity className="w-4 h-4 text-indigo-400" />
                <h3>CAS Intelligence</h3>
            </div>
            <div className="text-xs text-slate-400 leading-relaxed">
                The Closing Auction Session (CAS) model is currently monitoring cross-asset flows. 
                Check the <span className="text-indigo-400 underline cursor-pointer">CAS Signal tab</span> for the live directional bias.
            </div>
        </div>
      </div>

      {/* CENTER COLUMN: Execution & Analysis (6 cols) */}
      <div className="lg:col-span-6 space-y-6">
        <SignalCard 
          signal={signalData.signal}
          confidence={signalData.confidence}
          bullConfidence={signalData.bull_confidence}
          bearConfidence={signalData.bear_confidence}
        />

        <SignalComparisonCard mainSignal={signalData} />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <StrikeCard strikes={signalData.strikes} signal={signalData.signal} />
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
                <div className="flex items-center space-x-2 mb-4 text-slate-200 font-bold text-sm">
                    <Zap className="w-4 h-4 text-yellow-400" />
                    <h3>Execution Strategy</h3>
                </div>
                <div className="space-y-3">
                    <div className="flex justify-between text-xs">
                        <span className="text-slate-500">Recommended Entry</span>
                        <span className="text-slate-200 font-mono">{signalData.signal === 'STAY OUT' ? 'Wait' : 'Limit Order'}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                        <span className="text-slate-500">Target DTE</span>
                        <span className="text-slate-200 font-mono">{signalData.dte} Days</span>
                    </div>
                    <div className="flex justify-between text-xs">
                        <span className="text-slate-500">Expected Move</span>
                        <span className="text-slate-200 font-mono">±{Math.round(signalData.vix * Math.sqrt(signalData.dte/365) * 100 / 100)}%</span>
                    </div>
                </div>
            </div>
        </div>

        <IndicatorBoard 
          indicators={signalData.indicators}
          expanded={expandedIndicator}
          onToggle={setExpandedIndicator}
        />
      </div>

      {/* RIGHT COLUMN: Risk & Portfolio (3 cols) */}
      <div className="lg:col-span-3 space-y-6">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
            <div className="flex items-center space-x-2 mb-4 text-slate-200 font-bold text-sm">
                <ShieldAlert className="w-4 h-4 text-red-400" />
                <h3>Portfolio Greeks</h3>
            </div>
            <div className="grid grid-cols-2 gap-3">
                <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700">
                    <div className="text-slate-500 text-[10px] uppercase font-bold mb-1">Net Delta</div>
                    <div className="text-lg font-mono text-slate-200">{portfolioGreeks?.portfolio_delta || '0.00'}</div>
                </div>
                <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700">
                    <div className="text-slate-500 text-[10px] uppercase font-bold mb-1">Net Gamma</div>
                    <div className="text-lg font-mono text-slate-200">{portfolioGreeks?.portfolio_gamma || '0.00'}</div>
                </div>
                <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700">
                    <div className="text-slate-500 text-[10px] uppercase font-bold mb-1">Net Vega</div>
                    <div className="text-lg font-mono text-slate-200">{portfolioGreeks?.portfolio_vega || '0.00'}</div>
                </div>
                <div className="bg-slate-800/50 p-3 rounded-lg border border-slate-700">
                    <div className="text-slate-500 text-[10px] uppercase font-bold mb-1">Net Theta</div>
                    <div className="text-lg font-mono text-slate-200">{portfolioGreeks?.portfolio_theta || '0.00'}</div>
                </div>
            </div>
            <div className="mt-4 p-2 bg-slate-800/30 rounded border border-slate-700 text-[10px] text-slate-500 text-center">
                Connect Zerodha/IBKR to see live portfolio Greeks
            </div>
        </div>

        <MarketContext />
        
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4">
            <div className="flex items-center space-x-2 mb-3 text-slate-200 font-bold text-sm">
                <Layers className="w-4 h-4 text-indigo-400" />
                <h3>Risk Profile</h3>
            </div>
            <div className="space-y-2">
                <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Directional Risk</span>
                    <span className="text-green-400 font-medium">Low</span>
                </div>
                <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Volatility Risk</span>
                    <span className="text-yellow-400 font-medium">Moderate</span>
                </div>
                <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Time Decay Risk</span>
                    <span className="text-slate-200 font-medium">Neutral</span>
                </div>
            </div>
        </div>
      </div>
    </div>
  );
}
