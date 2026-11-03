import React, { useState, useEffect } from 'react';
import { RefreshCw, TrendingUp, TrendingDown, AlertTriangle, Clock, Activity, Target, ShieldCheck, Lightbulb } from 'lucide-react';

const API_BASE = 'http://localhost:8001';

function PCRGauge({ pcr, signal }) {
  const color = signal === 'BULLISH' ? '#00d4aa' : signal === 'BEARISH' ? '#ff4757' : '#ffa502';
  const label = signal === 'BULLISH'
    ? 'Contrarian Bullish — heavy put writing'
    : signal === 'BEARISH'
    ? 'Contrarian Bearish — heavy call writing'
    : 'Neutral sentiment';

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-5">
      <p className="text-xs text-[#546e7a] mb-1">Put-Call Ratio (PCR)</p>
      <div className="flex items-end gap-3">
        <p className="text-4xl font-bold font-mono" style={{ color }}>{pcr?.toFixed(2)}</p>
        <span className="text-sm mb-1" style={{ color }}>{signal}</span>
      </div>
      <p className="text-xs text-[#546e7a] mt-2">{label}</p>
      <div className="mt-3 h-2 bg-[#1a2035] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{
            width: `${Math.min(100, (pcr / 2) * 100)}%`,
            backgroundColor: color
          }}
        />
      </div>
      <div className="flex justify-between text-xs text-[#546e7a] mt-1">
        <span>0.5 (Bearish)</span>
        <span>1.0 (Neutral)</span>
        <span>1.5+ (Bullish)</span>
      </div>
    </div>
  );
}

function MaxPainCard({ maxPain, spot }) {
  const diff = maxPain - spot;
  const pct = ((diff / spot) * 100).toFixed(2);
  const direction = diff > 0 ? 'above' : 'below';
  const color = diff > 0 ? '#00d4aa' : '#ff4757';

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-5">
      <p className="text-xs text-[#546e7a] mb-1">Max Pain Strike</p>
      <p className="text-4xl font-bold font-mono text-[#ffa502]">{maxPain?.toLocaleString('en-IN')}</p>
      <p className="text-xs mt-2" style={{ color }}>
        {Math.abs(diff).toFixed(0)} pts ({Math.abs(pct)}%) {direction} spot
      </p>
      <p className="text-xs text-[#546e7a] mt-1">
        Market tends to gravitate toward max pain at expiry
      </p>
    </div>
  );
}

function DTECard({ dte, expiry }) {
  const color = dte <= 1 ? '#ff4757' : dte <= 2 ? '#ffa502' : '#00d4aa';
  const warning = dte <= 1
    ? '⚠️ Expiry tomorrow — avoid new entries'
    : dte <= 2
    ? '⚠️ Low DTE — use ATM only, tight stops'
    : 'Safe to enter new positions';

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-5">
      <p className="text-xs text-[#546e7a] mb-1">Days to Expiry</p>
      <p className="text-4xl font-bold font-mono" style={{ color }}>{dte}</p>
      <p className="text-xs text-[#546e7a] mt-1">Expiry: {expiry}</p>
      <p className="text-xs mt-2" style={{ color }}>{warning}</p>
    </div>
  );
}

function AnalysisCard({ analysis }) {
  if (!analysis) return null;
  const biasColor = analysis.overall_bias === 'BULLISH' ? '#00d4aa' : analysis.overall_bias === 'BEARISH' ? '#ff4757' : '#ffa502';

  return (
    <div className="bg-[#0f1629] border-2 border-[#00d4aa]/30 rounded-lg p-5">
      <h3 className="text-sm font-bold text-[#e8eaf6] mb-3 flex items-center gap-2">
        <Lightbulb className="w-4 h-4 text-[#00d4aa]" />
        Chain Analysis & Suggested Approach
      </h3>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
        <div className="bg-[#0a0e1a] border border-[#1a2035] rounded p-3">
          <p className="text-[10px] text-[#546e7a] uppercase flex items-center gap-1">
            <ShieldCheck className="w-3 h-3" /> OI-Wall Support
          </p>
          <p className="text-xl font-mono font-bold text-[#00d4aa]">{analysis.support ?? '—'}</p>
        </div>
        <div className="bg-[#0a0e1a] border border-[#1a2035] rounded p-3">
          <p className="text-[10px] text-[#546e7a] uppercase flex items-center gap-1">
            <Target className="w-3 h-3" /> OI-Wall Resistance
          </p>
          <p className="text-xl font-mono font-bold text-[#ff4757]">{analysis.resistance ?? '—'}</p>
        </div>
        <div className="bg-[#0a0e1a] border border-[#1a2035] rounded p-3">
          <p className="text-[10px] text-[#546e7a] uppercase">Overall OI Bias</p>
          <p className="text-xl font-mono font-bold" style={{ color: biasColor }}>{analysis.overall_bias}</p>
          {analysis.range_width_pct != null && (
            <p className="text-[10px] text-[#546e7a] mt-0.5">Range: {analysis.range_width_points}pts ({analysis.range_width_pct}%)</p>
          )}
        </div>
      </div>

      {(analysis.avg_call_iv != null || analysis.avg_put_iv != null) && (
        <div className="flex gap-6 mb-3 text-xs">
          <span className="text-[#546e7a]">
            Avg Call IV: <span className="text-[#00d4aa] font-mono font-bold">{analysis.avg_call_iv ?? '—'}%</span>
          </span>
          <span className="text-[#546e7a]">
            Avg Put IV: <span className="text-[#ff4757] font-mono font-bold">{analysis.avg_put_iv ?? '—'}%</span>
          </span>
        </div>
      )}

      <div className="bg-[#00d4aa]/5 border border-[#00d4aa]/20 rounded p-3 mb-3">
        <p className="text-xs text-[#e8eaf6] leading-relaxed">
          <span className="font-bold text-[#00d4aa]">Suggested approach: </span>
          {analysis.suggested_action}
        </p>
      </div>

      <div className="space-y-1.5">
        {analysis.reasoning?.map((r, i) => (
          <p key={i} className="text-[11px] text-[#8892a6] flex items-start gap-1.5">
            <span className="text-[#546e7a] mt-0.5">•</span> {r}
          </p>
        ))}
      </div>

      <p className="text-[10px] text-[#3a4356] mt-3 italic">
        Derived purely from live OI/PCR/Max-Pain structure — cross-check against the CAS Signal
        and main technical signal tabs before acting. Not a guaranteed outcome.
      </p>
    </div>
  );
}

function OITable({ title, data, type }) {
  const color = type === 'CE' ? '#00d4aa' : '#ff4757';
  const bgColor = type === 'CE' ? 'bg-[#00d4aa]/5' : 'bg-[#ff4757]/5';

  if (!data || data.length === 0) return null;

  const maxOI = Math.max(...data.map(d => d.oi));

  return (
    <div className={`bg-[#0f1629] border border-[#1a2035] rounded-lg p-5`}>
      <h3 className="text-sm font-bold mb-3 flex items-center gap-2" style={{ color }}>
        {type === 'CE' ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
        Top {type} Strikes by OI
        <span className="text-xs text-[#546e7a] font-normal">(resistance/support levels)</span>
      </h3>
      <div className="space-y-2">
        {data.map((item, i) => (
          <div key={i} className="relative">
            <div className="flex justify-between items-center text-xs mb-1">
              <span className="font-mono font-bold text-[#e8eaf6]">{item.strike?.toLocaleString('en-IN')} {type}</span>
              <div className="flex gap-4 text-[#546e7a]">
                <span>OI: <span className="text-[#e8eaf6] font-mono">{(item.oi / 100000).toFixed(1)}L</span></span>
                {item.oi_change !== 0 && (
                  <span className={item.oi_change > 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]'}>
                    {item.oi_change > 0 ? '+' : ''}{(item.oi_change / 100000).toFixed(1)}L
                  </span>
                )}
                {item.iv > 0 && <span>IV: <span className="text-[#ffa502] font-mono">{item.iv?.toFixed(1)}%</span></span>}
              </div>
            </div>
            <div className="h-1.5 bg-[#1a2035] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(item.oi / maxOI) * 100}%`,
                  backgroundColor: color
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function OptionsChain() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastFetched, setLastFetched] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/options-chain`);
      const json = await response.json();
      if (json.error) {
        setError(json.message || json.error);
      } else {
        setData(json);
        setLastFetched(new Date());
      }
    } catch (err) {
      setError('Failed to connect to backend. Make sure the server is running.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-[#e8eaf6]">NSE Options Chain</h2>
          <p className="text-sm text-[#546e7a] mt-1">
            Live PCR, Max Pain, OI buildup — free from NSE India
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastFetched && (
            <span className="text-xs text-[#546e7a] flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {lastFetched.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center gap-2 bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-4 py-2 rounded text-sm hover:border-[#00d4aa] transition disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-[#ff4757]/10 border border-[#ff4757]/30 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-[#ff4757] flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-[#ff4757] font-semibold text-sm">Failed to fetch options data</p>
            <p className="text-[#546e7a] text-xs mt-1">{error}</p>
            <p className="text-[#546e7a] text-xs mt-1">
              NSE may be closed (market hours: 9:15 AM – 3:30 PM IST) or rate-limiting requests.
            </p>
          </div>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && !data && (
        <div className="space-y-4 animate-pulse">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="h-32 bg-[#0f1629] rounded-lg" />
            <div className="h-32 bg-[#0f1629] rounded-lg" />
            <div className="h-32 bg-[#0f1629] rounded-lg" />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="h-64 bg-[#0f1629] rounded-lg" />
            <div className="h-64 bg-[#0f1629] rounded-lg" />
          </div>
        </div>
      )}

      {/* Data */}
      {data && (
        <>
          {/* Key metrics row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <PCRGauge pcr={data.pcr} signal={data.pcr_signal} />
            <MaxPainCard maxPain={data.max_pain} spot={data.spot_price} />
            <DTECard dte={data.days_to_expiry} expiry={data.nearest_expiry} />
          </div>

          {/* Actionable analysis — support/resistance from OI walls, bias, IV skew, suggested approach */}
          <AnalysisCard analysis={data.analysis} />

          {/* OI summary */}
          <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-4 flex flex-wrap gap-6 text-sm">
            <span className="text-[#546e7a]">
              Spot: <span className="text-[#e8eaf6] font-mono font-bold">
                {data.spot_price?.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </span>
            </span>
            <span className="text-[#546e7a]">
              Total CE OI: <span className="text-[#00d4aa] font-mono font-bold">
                {(data.total_call_oi / 100000)?.toFixed(1)}L
              </span>
            </span>
            <span className="text-[#546e7a]">
              Total PE OI: <span className="text-[#ff4757] font-mono font-bold">
                {(data.total_put_oi / 100000)?.toFixed(1)}L
              </span>
            </span>
            <span className="text-[#546e7a]">
              Expiry: <span className="text-[#ffa502] font-mono font-bold">{data.nearest_expiry}</span>
            </span>
          </div>

          {/* OI Tables */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <OITable title="Top Call OI" data={data.top_call_oi} type="CE" />
            <OITable title="Top Put OI" data={data.top_put_oi} type="PE" />
          </div>

          {/* Interpretation guide */}
          <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-5">
            <h3 className="text-sm font-bold text-[#e8eaf6] mb-3 flex items-center gap-2">
              <Activity className="w-4 h-4 text-[#ffa502]" />
              How to Read This Data
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs text-[#546e7a]">
              <div className="space-y-2">
                <p><span className="text-[#00d4aa]">PCR &gt; 1.2</span> — More puts than calls = bearish sentiment = contrarian bullish signal. Market makers are net short puts.</p>
                <p><span className="text-[#ff4757]">PCR &lt; 0.8</span> — More calls than puts = bullish sentiment = contrarian bearish signal. Market makers are net short calls.</p>
                <p><span className="text-[#ffa502]">Max Pain</span> — The strike where option sellers (market makers) lose the least money. Market tends to pin near this level at expiry.</p>
              </div>
              <div className="space-y-2">
                <p><span className="text-[#00d4aa]">High CE OI at a strike</span> — Strong resistance. Market makers will defend this level. Avoid buying CE above this strike.</p>
                <p><span className="text-[#ff4757]">High PE OI at a strike</span> — Strong support. Market makers will defend this level. Avoid buying PE below this strike.</p>
                <p><span className="text-[#e8eaf6]">OI Change</span> — Fresh OI addition (green) = new positions being built. OI reduction = positions being closed.</p>
              </div>
            </div>
          </div>
        </>
      )}

      {!data && !loading && !error && (
        <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-12 text-center text-[#546e7a]">
          <Activity className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>Click Refresh to load live options chain data</p>
        </div>
      )}
    </div>
  );
}
