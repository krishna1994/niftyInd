import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  Layers, RefreshCw, AlertTriangle, TrendingUp, TrendingDown,
  CheckCircle2, XCircle, Target, Activity, Info,
} from 'lucide-react';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ReferenceLine,
} from 'recharts';

const API_BASE = 'http://localhost:8001';
const DEBOUNCE_MS = 350; // wait this long after the user stops moving a slider before re-fetching strikes from the live NSE chain

function StatBox({ label, value, color, sub }) {
  return (
    <div className="bg-[#0a0e1a] border border-[#1a2035] rounded-lg p-3">
      <p className="text-[10px] text-[#546e7a] uppercase">{label}</p>
      <p className="text-lg font-mono font-bold" style={{ color: color || '#e8eaf6' }}>{value}</p>
      {sub && <p className="text-[10px] text-[#546e7a] mt-0.5">{sub}</p>}
    </div>
  );
}

function LegRow({ role, leg }) {
  const isSell = leg.action === 'SELL';
  return (
    <div className="flex items-center justify-between bg-[#0a0e1a] border border-[#1a2035] rounded-lg p-3">
      <div className="flex items-center gap-3">
        <span
          className={`text-xs font-bold px-2 py-1 rounded ${
            isSell ? 'bg-[#ff4757]/15 text-[#ff4757]' : 'bg-[#00d4aa]/15 text-[#00d4aa]'
          }`}
        >
          {leg.action}
        </span>
        <span className="text-sm text-[#e8eaf6] font-mono">{leg.strike} {role.includes('call') ? 'CE' : 'PE'}</span>
      </div>
      <div className="text-right text-xs">
        <span className="text-[#546e7a]">LTP </span>
        <span className="text-[#e8eaf6] font-mono font-bold">₹{leg.ltp}</span>
        <span className="text-[#546e7a] ml-3">IV </span>
        <span className="text-[#e8eaf6] font-mono">{leg.iv}%</span>
      </div>
    </div>
  );
}

// Fallback spot price used ONLY for the very first points<->percent
// conversion before the first live suggestion has loaded (afterwards we
// always use the real live strikes.spot_price).
const FALLBACK_SPOT = 24000;

export default function IronCondor() {
  // otmPoints/wingWidth are the DEBOUNCED values actually sent to the
  // backend. draftOtmPoints/draftWingWidth track the control's live value
  // instantly (for smooth dragging/typing) without firing a network
  // request on every pixel/keystroke.
  //
  // Short strike distance is specified in POINTS (more intuitive for
  // options traders than a percentage) — otmPoints/draftOtmPoints are the
  // primary values the user interacts with (via both a slider AND a
  // direct number input, kept in sync with each other). The equivalent
  // percent is derived from otmPoints + the live spot price purely to
  // talk to the backend API (which is percent-based).
  const [otmPoints, setOtmPoints] = useState(600);
  const [draftOtmPoints, setDraftOtmPoints] = useState(600);
  const [wingWidth, setWingWidth] = useState(200);
  const [draftWingWidth, setDraftWingWidth] = useState(200);

  // lots and balance are PURE client-side inputs — changing them never
  // triggers a network call, since margin/P&L scale linearly and are
  // computed instantly below via useMemo.
  const [lots, setLots] = useState(1);
  const [manualBalance, setManualBalance] = useState('');
  const [balanceTouched, setBalanceTouched] = useState(false);

  const [strikes, setStrikes] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [liveStatus, setLiveStatus] = useState(null);
  const [recommendation, setRecommendation] = useState(null);

  const [placing, setPlacing] = useState(false);
  const [placeResult, setPlaceResult] = useState(null);
  const [confirmText, setConfirmText] = useState('');

  const debounceRef = useRef(null);

  // Live spot price used to convert points<->percent for the backend API
  // (backend is percent-based; the UI is points-based per user preference).
  // Falls back to a reasonable constant before the first suggestion loads.
  const currentSpot = strikes?.spot_price || FALLBACK_SPOT;

  const fetchSuggestion = useCallback(async (points, wing) => {
    setLoading(true);
    setError(null);
    try {
      const spotForConversion = strikes?.spot_price || FALLBACK_SPOT;
      const otmPctForApi = (points / spotForConversion) * 100;
      const res = await fetch(
        `${API_BASE}/api/iron-condor/suggest?otm_distance_pct=${otmPctForApi}&wing_width_points=${wing}`
      );
      const data = await res.json();
      if (!data.success) {
        setError(data.message || 'Could not fetch iron condor suggestion.');
        setStrikes(null);
      } else {
        setStrikes(data);
        // Pre-fill the balance field with the live Zerodha balance ONLY the
        // first time we see it and the user hasn't typed anything yet —
        // never overwrite what the user is actively editing.
        if (!balanceTouched && data.live_available_balance != null) {
          setManualBalance(String(Math.round(data.live_available_balance)));
        }
      }
    } catch (e) {
      setError('Could not reach backend.');
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [balanceTouched, strikes?.spot_price]);

  // Initial load
  useEffect(() => {
    fetchSuggestion(otmPoints, wingWidth);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Debounced re-fetch whenever the COMMITTED otmPoints/wingWidth change
  // (these only change after the debounce timer below fires)
  useEffect(() => {
    fetchSuggestion(otmPoints, wingWidth);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [otmPoints, wingWidth]);

  // Short strike distance: BOTH a slider AND a direct number input update
  // the same draft value instantly (smooth dragging/typing), and both are
  // debounced the same way before triggering the (NSE-chain-fetching)
  // network request.
  const handleOtmChange = (value) => {
    const points = Math.max(0, Number(value) || 0);
    setDraftOtmPoints(points);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setOtmPoints(points), DEBOUNCE_MS);
  };

  const handleWingDrag = (value) => {
    setDraftWingWidth(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setWingWidth(value), DEBOUNCE_MS);
  };

  const fetchLiveStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/iron-condor/live-status`);
      setLiveStatus(await res.json());
    } catch (e) {
      setLiveStatus(null);
    }
  }, []);

  const fetchRecommendation = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/iron-condor/recommendation`);
      setRecommendation(await res.json());
    } catch (e) {
      setRecommendation(null);
    }
  }, []);

  useEffect(() => {
    fetchLiveStatus();
    const interval = setInterval(fetchLiveStatus, 20000);
    return () => clearInterval(interval);
  }, [fetchLiveStatus]);

  useEffect(() => {
    fetchRecommendation();
  }, [fetchRecommendation]);

  const applyRecommended = () => {
    if (!recommendation) return;
    // Backend recommendation is percent-based — convert to points using the
    // current live spot so the UI stays consistently points-based.
    const recPoints = Math.round((recommendation.recommended_otm_distance_pct / 100) * currentSpot);
    setDraftOtmPoints(recPoints);
    setDraftWingWidth(recommendation.recommended_wing_width_points);
    setOtmPoints(recPoints);
    setWingWidth(recommendation.recommended_wing_width_points);
  };

  // ── Instant client-side derived numbers — NO network call involved ──────
  // Everything that depends on `lots` or `manualBalance` is computed here,
  // so typing a balance or changing the lot count updates the UI on every
  // keystroke with zero lag/flicker, using the per-share/per-lot figures
  // already returned by the one strikes fetch above.
  const derived = useMemo(() => {
    if (!strikes) return null;
    const lotSize = strikes.lot_size || 75;
    const maxProfitTotal = strikes.max_profit_per_share * lotSize * lots;
    const maxLossTotal = strikes.max_loss_per_share * lotSize * lots;
    const marginPerLot = strikes.margin_per_lot; // per 1 lot, from backend
    const requiredMargin = marginPerLot != null ? marginPerLot * lots : null;

    const balanceNum = manualBalance !== '' && !isNaN(Number(manualBalance)) ? Number(manualBalance) : null;
    let sufficient = null;
    let shortfall = null;
    let suggestedMaxLots = null;
    if (balanceNum != null && marginPerLot != null) {
      sufficient = requiredMargin != null ? balanceNum >= requiredMargin : null;
      shortfall = requiredMargin != null ? Math.max(0, requiredMargin - balanceNum) : null;
      suggestedMaxLots = marginPerLot > 0 ? Math.floor(balanceNum / marginPerLot) : 0;
    }

    return {
      lotSize,
      totalQuantity: lotSize * lots,
      maxProfitTotal,
      maxLossTotal,
      marginPerLot,
      marginSource: strikes.margin_source,
      requiredMargin,
      balanceNum,
      sufficient,
      shortfall,
      suggestedMaxLots,
    };
  }, [strikes, lots, manualBalance]);

  const handlePlace = async () => {
    if (confirmText !== 'PLACE') {
      setPlaceResult({ success: false, errors: ['Type PLACE in the confirmation box first — this executes 4 REAL orders with real money.'] });
      return;
    }
    setPlacing(true);
    setPlaceResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/iron-condor/place`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          otm_distance_pct: (otmPoints / currentSpot) * 100,
          wing_width_points: wingWidth,
          strike_step: 50,
          lots,
        }),
      });
      const data = await res.json();
      setPlaceResult(data);
      setConfirmText('');
      await fetchLiveStatus();
    } catch (e) {
      setPlaceResult({ success: false, errors: [e.message] });
    } finally {
      setPlacing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-[#e8eaf6] flex items-center gap-2">
            <Layers className="w-5 h-5 text-[#00d4aa]" />
            Short Iron Condor
          </h2>
          <p className="text-sm text-[#546e7a] mt-1">
            Defined-risk, range-bound premium-selling strategy — sell OTM call + put, hedge with further OTM long call + put.
          </p>
        </div>
        <button
          onClick={() => fetchSuggestion(otmPoints, wingWidth)}
          disabled={loading}
          className="flex items-center gap-2 bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-4 py-2 rounded-xl text-sm hover:border-[#00d4aa] transition disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh Suggestion
        </button>
      </div>

      {/* Live existing IC monitor — only shows if a matching position is detected */}
      {liveStatus?.detected && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-[#0f1629] border border-[#00d4aa]/30 rounded-2xl p-5"
        >
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide flex items-center gap-2">
              <Activity className="w-3.5 h-3.5" /> Your Existing Iron Condor (Live)
            </p>
            <span
              className="text-lg font-mono font-bold"
              style={{ color: liveStatus.total_pnl >= 0 ? '#00d4aa' : '#ff4757' }}
            >
              {liveStatus.total_pnl >= 0 ? '+' : ''}₹{liveStatus.total_pnl}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 mb-3">
            <StatBox label="Short Call Strike" value={liveStatus.short_call_strike} />
            <StatBox label="Short Put Strike" value={liveStatus.short_put_strike} />
          </div>
          <div className="grid grid-cols-4 gap-2 mb-3">
            {liveStatus.legs?.map((leg, i) => (
              <div key={i} className="bg-[#0a0e1a] rounded p-2 text-center">
                <p className="text-[9px] text-[#546e7a] uppercase">{leg.role.replace('_', ' ')}</p>
                <p
                  className="text-xs font-mono font-bold"
                  style={{ color: leg.pnl >= 0 ? '#00d4aa' : '#ff4757' }}
                >
                  {leg.pnl >= 0 ? '+' : ''}₹{leg.pnl}
                </p>
              </div>
            ))}
          </div>
          {liveStatus.alerts?.length > 0 && (
            <div className="space-y-1.5">
              {liveStatus.alerts.map((alert, i) => (
                <div
                  key={i}
                  className={`rounded p-2 text-xs flex items-start gap-1.5 ${
                    alert.severity === 'danger'
                      ? 'bg-[#ff4757]/10 border border-[#ff4757]/40 text-[#ff4757]'
                      : 'bg-[#ffa502]/10 border border-[#ffa502]/40 text-[#ffa502]'
                  }`}
                >
                  <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                  {alert.message}
                </div>
              ))}
            </div>
          )}
        </motion.div>
      )}

      {error && (
        <div className="bg-[#ff4757]/10 border border-[#ff4757]/30 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-[#ff4757] flex-shrink-0 mt-0.5" />
          <p className="text-[#ff4757] text-sm">{error}</p>
        </div>
      )}

      {/* Backtested recommendation for today's day of week */}
      {recommendation && (
        <div className="bg-[#0f1629] border border-[#00d4aa]/30 rounded-2xl p-5">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div>
              <p className="text-xs font-bold text-[#00d4aa] uppercase tracking-wide flex items-center gap-2">
                <Activity className="w-3.5 h-3.5" /> Recommended for Today ({recommendation.today})
              </p>
              <p className="text-sm text-[#e8eaf6] mt-1">
                {recommendation.recommended_otm_distance_pct}% OTM, {recommendation.recommended_wing_width_points}pt wings
              </p>
              <p className="text-xs text-[#546e7a] mt-1">{recommendation.note}</p>
            </div>
            <button
              onClick={applyRecommended}
              className="bg-[#00d4aa]/15 border border-[#00d4aa]/40 text-[#00d4aa] px-4 py-2 rounded text-sm font-semibold hover:bg-[#00d4aa]/25 transition flex-shrink-0"
            >
              Use Recommended
            </button>
          </div>
          <p className="text-[10px] text-[#546e7a] mt-3">
            Based on a 2-year, 104-weekly-cycle historical backtest, dynamically scaled to today's
            actual days-to-expiry and live IV — see <code>backend/IRON_CONDOR_BACKTEST_FINDINGS.md</code>.
            Past performance does not guarantee future outcomes.
          </p>
        </div>
      )}

      {/* Config controls */}
      <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5 grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-semibold text-[#e8eaf6] block">
              Short Strike Distance
            </label>
            <div className="flex items-center gap-1">
              <input
                type="number" min="0" max="3000" step="25"
                value={draftOtmPoints}
                onChange={(e) => handleOtmChange(e.target.value)}
                className="w-20 bg-[#1a2035] border border-[#1a2035] rounded px-2 py-0.5 text-xs text-[#e8eaf6] text-right"
              />
              <span className="text-xs text-[#546e7a]">pts OTM</span>
            </div>
          </div>
          <input
            type="range" min="0" max="3000" step="25"
            value={draftOtmPoints}
            onChange={(e) => handleOtmChange(e.target.value)}
            className="w-full accent-[#00d4aa]"
          />
          <p className="text-[10px] text-[#546e7a] mt-1">
            ≈ {((draftOtmPoints / currentSpot) * 100).toFixed(2)}% OTM at current spot
          </p>
        </div>
        <div>
          <label className="text-xs font-semibold text-[#e8eaf6] mb-1.5 block">
            Wing Width: {draftWingWidth} pts
          </label>
          <input
            type="range" min="50" max="500" step="50"
            value={draftWingWidth}
            onChange={(e) => handleWingDrag(Number(e.target.value))}
            className="w-full accent-[#ffa502]"
          />
        </div>
        <div>
          <label className="text-xs font-semibold text-[#e8eaf6] mb-1.5 block">Lots</label>
          <input
            type="number" min="1" max="20"
            value={lots}
            onChange={(e) => setLots(Math.max(1, Number(e.target.value) || 1))}
            className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-sm text-[#e8eaf6]"
          />
          <p className="text-[10px] text-[#546e7a] mt-1">Updates instantly — no reload needed</p>
        </div>
      </div>

      {strikes && (
        <>
          {/* Key stats */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
            <StatBox label="Spot" value={strikes.spot_price?.toLocaleString('en-IN')} />
            <StatBox
              label="Max Profit"
              value={`₹${derived.maxProfitTotal.toFixed(0)}`}
              color="#00d4aa"
              sub={`₹${strikes.max_profit_per_share}/share`}
            />
            <StatBox
              label="Max Loss"
              value={`₹${derived.maxLossTotal.toFixed(0)}`}
              color="#ff4757"
              sub={`₹${strikes.max_loss_per_share}/share`}
            />
            <StatBox
              label="Probability of Profit"
              value={strikes.probability_of_profit != null ? `${Math.round(strikes.probability_of_profit * 100)}%` : '—'}
              color="#ffa502"
            />
            <StatBox label="Days to Expiry" value={strikes.days_to_expiry} sub={strikes.expiry} />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <StatBox label="Upper Breakeven" value={strikes.upper_breakeven} color="#ff4757" />
            <StatBox label="Lower Breakeven" value={strikes.lower_breakeven} color="#ff4757" />
          </div>

          {/* Lot size + Balance/Margin check — all instant, client-side */}
          <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5">
            <div className="flex items-center justify-between flex-wrap gap-3 mb-3">
              <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide flex items-center gap-2">
                <Info className="w-3.5 h-3.5" /> Position Size & Margin
              </p>
              <div className="flex items-center gap-2">
                <label className="text-[10px] text-[#546e7a]">Available balance (₹):</label>
                <input
                  type="number"
                  min="0"
                  placeholder="e.g. 50000"
                  value={manualBalance}
                  onChange={(e) => {
                    setBalanceTouched(true);
                    setManualBalance(e.target.value);
                  }}
                  className="bg-[#1a2035] border border-[#1a2035] rounded px-2 py-1 text-xs text-[#e8eaf6] w-32"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatBox label="Lot Size (live)" value={derived.lotSize} sub="from Zerodha, auto-updates if NSE revises it" />
              <StatBox label="Total Quantity" value={derived.totalQuantity} sub={`${lots} lot(s)`} />
              <StatBox
                label="Margin / Lot"
                value={derived.marginPerLot != null ? `₹${derived.marginPerLot.toLocaleString('en-IN')}` : '—'}
                color="#ffa502"
                sub={derived.marginSource === 'live' ? 'live (Zerodha)' : 'approximate (max-loss based)'}
              />
              <StatBox
                label="Required Margin"
                value={derived.requiredMargin != null ? `₹${derived.requiredMargin.toLocaleString('en-IN')}` : '—'}
                color="#ffa502"
                sub={`for ${lots} lot(s)`}
              />
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mt-3">
              {derived.balanceNum != null ? (
                <>
                  <StatBox
                    label="Available Balance"
                    value={`₹${derived.balanceNum.toLocaleString('en-IN')}`}
                    color={derived.sufficient ? '#00d4aa' : '#ff4757'}
                  />
                  <StatBox
                    label={derived.sufficient ? 'Sufficient?' : 'Shortfall'}
                    value={derived.sufficient ? 'Yes ✓' : `₹${derived.shortfall.toLocaleString('en-IN')}`}
                    color={derived.sufficient ? '#00d4aa' : '#ff4757'}
                  />
                  <StatBox
                    label="Max Affordable Lots"
                    value={derived.suggestedMaxLots}
                    color="#00d4aa"
                    sub="at current balance"
                  />
                </>
              ) : (
                <div className="col-span-3 flex items-center">
                  <p className="text-xs text-[#546e7a]">
                    Enter your available balance above to see sufficiency check and max affordable lots.
                  </p>
                </div>
              )}
            </div>

            {derived.sufficient === false && (
              <div className="mt-3 bg-[#ff4757]/10 border border-[#ff4757]/30 rounded p-2 text-xs text-[#ff4757] flex items-start gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                Insufficient balance for {lots} lot(s) — try {derived.suggestedMaxLots} lot(s) instead, or add funds before placing this trade.
              </div>
            )}
            {derived.marginSource === 'approximate' && (
              <p className="text-[10px] text-[#546e7a] mt-3">
                Margin/lot is an approximate estimate based on max possible loss (Zerodha not
                connected or session expired) — connect Zerodha for the exact live cross-margined figure.
              </p>
            )}
          </div>

          {/* Legs */}
          <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5">
            <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide mb-3 flex items-center gap-2">
              <Target className="w-3.5 h-3.5" /> The 4 Legs
            </p>
            <div className="space-y-2">
              <LegRow role="long_call" leg={strikes.legs.long_call} />
              <LegRow role="short_call" leg={strikes.legs.short_call} />
              <LegRow role="short_put" leg={strikes.legs.short_put} />
              <LegRow role="long_put" leg={strikes.legs.long_put} />
            </div>
          </div>

          {/* Payoff diagram */}
          <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-5">
            <p className="text-xs font-bold text-[#546e7a] uppercase tracking-wide mb-3 flex items-center gap-2">
              <TrendingUp className="w-3.5 h-3.5" /> Payoff Diagram (at expiry)
            </p>
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={strikes.payoff_diagram}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1a2035" />
                <XAxis dataKey="spot" stroke="#546e7a" fontSize={11} />
                <YAxis stroke="#546e7a" fontSize={11} />
                <Tooltip
                  contentStyle={{ background: '#0a0e1a', border: '1px solid #1a2035', borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: '#e8eaf6' }}
                />
                <ReferenceLine y={0} stroke="#546e7a" strokeDasharray="3 3" />
                <ReferenceLine x={strikes.spot_price} stroke="#00d4aa" strokeDasharray="3 3" label={{ value: 'Spot', fill: '#00d4aa', fontSize: 10 }} />
                <Area
                  type="monotone"
                  dataKey="pnl"
                  stroke="#00d4aa"
                  fill="#00d4aa"
                  fillOpacity={0.15}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Place order */}
          <div className="bg-[#0f1629] border-2 border-[#ff4757]/30 rounded-2xl p-5 space-y-3">
            <p className="text-sm font-bold text-[#ff4757] flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> Places 4 REAL orders with real money
            </p>
            <p className="text-xs text-[#546e7a]">
              Executes SELL {strikes.legs.short_call.strike}CE, BUY {strikes.legs.long_call.strike}CE, SELL{' '}
              {strikes.legs.short_put.strike}PE, BUY {strikes.legs.long_put.strike}PE as 4 separate market orders on
              your connected Zerodha account.
            </p>
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="Type PLACE to confirm"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                className="bg-[#1a2035] border border-[#ff4757]/30 rounded px-3 py-2 text-xs text-[#e8eaf6] w-48"
              />
              <button
                onClick={handlePlace}
                disabled={placing}
                className="bg-[#ff4757]/20 border border-[#ff4757] text-[#ff4757] px-4 py-2 rounded text-sm font-bold hover:bg-[#ff4757]/30 transition disabled:opacity-40"
              >
                {placing ? 'Placing...' : 'Place Iron Condor'}
              </button>
            </div>

            {placeResult && (
              <div
                className={`rounded p-3 text-xs ${
                  placeResult.success
                    ? 'bg-[#00d4aa]/10 border border-[#00d4aa]/30 text-[#00d4aa]'
                    : 'bg-[#ff4757]/10 border border-[#ff4757]/30 text-[#ff4757]'
                }`}
              >
                {placeResult.success ? (
                  <p className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> All 4 legs placed successfully.</p>
                ) : (
                  <div>
                    <p className="flex items-center gap-1.5 font-bold"><XCircle className="w-4 h-4" /> {placeResult.warning || 'Failed'}</p>
                    {placeResult.errors?.map((err, i) => <p key={i} className="mt-1">{err}</p>)}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="bg-[#0f1629] border border-[#1a2035] rounded-2xl p-4">
            <p className="text-[10px] text-[#546e7a] flex items-start gap-1.5">
              <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
              {strikes.note}
            </p>
          </div>
        </>
      )}
    </div>
  );
}