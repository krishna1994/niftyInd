import React, { useState, useEffect, useCallback } from 'react';
import {
  Save, Zap, CheckCircle2, RefreshCw, ExternalLink,
  Bell, Sliders, Palette, Database, Shield,
  AlertTriangle, Info, Unplug, Brain, Bot, XCircle, History, Key,
} from 'lucide-react';

const API_BASE = 'http://localhost:8001';

const DEFAULT_SETTINGS = {
  // Signal / strategy tuning
  confidenceThreshold: 65,
  vixMaxThreshold: 22,
  interval: '1d',
  strikeStep: 100,
  atrMultiplier: 1.5,
  slMultiplier: 1.5,
  targetMultiplier: 2.5,
  maxHoldDays: 5,
  lotSize: 75,

  // Refresh / notifications
  autoRefresh: true,
  refreshMinutes: 5,
  casAutoRefreshSeconds: 20,
  notifications: false,
  soundAlerts: false,

  // Display
  theme: 'dark',
  compactMode: false,
  showGreeks: false,

  // Risk management
  maxDailyLossPct: 5,
  maxOpenTrades: 3,
  requireHighConviction: false,
};

function SectionCard({ icon: Icon, title, subtitle, children }) {
  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
      <div className="flex items-center gap-2 mb-1">
        <Icon className="w-4 h-4 text-[#00d4aa]" />
        <h2 className="text-base font-bold text-[#e8eaf6]">{title}</h2>
      </div>
      {subtitle && <p className="text-xs text-[#546e7a] mb-5">{subtitle}</p>}
      <div className="space-y-5 mt-4">{children}</div>
    </div>
  );
}

function ToggleRow({ label, description, checked, onChange }) {
  return (
    <label className="flex items-start gap-3 cursor-pointer">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 mt-0.5 accent-[#00d4aa]"
      />
      <div>
        <span className="text-sm font-semibold text-[#e8eaf6] block">{label}</span>
        {description && <span className="text-xs text-[#546e7a]">{description}</span>}
      </div>
    </label>
  );
}

// ── Zerodha Integration Section ─────────────────────────────────────────────

function ZerodhaSection() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState(null);
  const [manualToken, setManualToken] = useState('');
  const [showManualEntry, setShowManualEntry] = useState(false);

  const [autoLoginStatus, setAutoLoginStatus] = useState(null);
  const [showAutoLogin, setShowAutoLogin] = useState(false);
  const [autoUserId, setAutoUserId] = useState('');
  const [autoPassword, setAutoPassword] = useState('');
  const [autoTotpSecret, setAutoTotpSecret] = useState('');
  const [autoLoginBusy, setAutoLoginBusy] = useState(false);
  const [autoLoginError, setAutoLoginError] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/status`);
      const data = await res.json();
      setStatus(data);
    } catch (e) {
      setStatus({ installed: false, configured: false, connected: false, message: 'Could not reach backend.' });
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAutoLoginStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/auto-login/status`);
      setAutoLoginStatus(await res.json());
    } catch (e) {
      setAutoLoginStatus(null);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchAutoLoginStatus();
  }, [fetchStatus, fetchAutoLoginStatus]);

  // Handle the OAuth redirect back from Zerodha: request_token appears as a
  // query param on this page (if the Kite Connect app's redirect URL points
  // here), so we auto-complete the login on mount if present.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const requestToken = params.get('request_token');
    if (requestToken) {
      (async () => {
        setConnecting(true);
        setError(null);
        try {
          const res = await fetch(`${API_BASE}/api/zerodha/callback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ request_token: requestToken }),
          });
          const data = await res.json();
          if (!res.ok) throw new Error(data.detail || 'Login failed');
          // Clean the URL so refreshing doesn't re-trigger the exchange
          window.history.replaceState({}, '', window.location.pathname);
          await fetchStatus();
        } catch (e) {
          setError(e.message);
        } finally {
          setConnecting(false);
        }
      })();
    }
  }, [fetchStatus]);

  const handleConnect = async () => {
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/login-url`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Could not get login URL');
      window.location.href = data.login_url;
    } catch (e) {
      setError(e.message);
    }
  };

  // Fallback for when the Kite Connect app's Redirect URL can't automatically
  // land back on this page (e.g. it requires https:// but this app runs on
  // plain http://localhost). After logging in, Zerodha still redirects to
  // whatever URL you configured — even if that page fails to load, the
  // request_token is visible in the browser's address bar. Paste it here.
  const handleManualSubmit = async () => {
    const token = manualToken.trim();
    if (!token) {
      setError('Paste the request_token value first.');
      return;
    }
    setConnecting(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/callback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request_token: token }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Login failed');
      setManualToken('');
      setShowManualEntry(false);
      await fetchStatus();
    } catch (e) {
      setError(e.message);
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await fetch(`${API_BASE}/api/zerodha/disconnect`, { method: 'POST' });
      await fetchStatus();
    } catch (e) {
      setError(e.message);
    }
  };

  const handleAutoLoginSubmit = async () => {
    if (!autoUserId || !autoPassword || !autoTotpSecret) {
      setAutoLoginError('All three fields are required.');
      return;
    }
    setAutoLoginBusy(true);
    setAutoLoginError(null);
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/auto-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: autoUserId,
          password: autoPassword,
          totp_secret: autoTotpSecret,
          remember: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Auto-login failed');
      setAutoPassword('');
      setAutoTotpSecret('');
      await fetchStatus();
      await fetchAutoLoginStatus();
    } catch (e) {
      setAutoLoginError(e.message);
    } finally {
      setAutoLoginBusy(false);
    }
  };

  const handleForgetAutoLogin = async () => {
    if (!window.confirm('Forget saved auto-login credentials?')) return;
    try {
      await fetch(`${API_BASE}/api/zerodha/auto-login/forget`, { method: 'POST' });
      setAutoUserId('');
      await fetchAutoLoginStatus();
    } catch (e) {
      setAutoLoginError(e.message);
    }
  };

  const badge = () => {
    if (loading) return null;
    if (status?.connected) {
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-[#00d4aa]/15 text-[#00d4aa] ring-1 ring-[#00d4aa]/30">
          <CheckCircle2 className="w-3.5 h-3.5" /> Connected
        </span>
      );
    }
    if (status?.configured) {
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-[#ffa502]/15 text-[#ffa502] ring-1 ring-[#ffa502]/30">
          <AlertTriangle className="w-3.5 h-3.5" /> Not Connected
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-[#546e7a]/15 text-[#546e7a] ring-1 ring-[#546e7a]/30">
        <Unplug className="w-3.5 h-3.5" /> Not Configured
      </span>
    );
  };

  return (
    <SectionCard
      icon={Zap}
      title="Zerodha Integration"
      subtitle="Connect your real Zerodha trading account for live positions, holdings, margins, quotes, and order placement."
    >
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          {badge()}
          {status?.connected && status.user_name && (
            <span className="text-sm text-[#e8eaf6]">
              {status.user_name} <span className="text-[#546e7a]">({status.user_id})</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchStatus}
            className="p-2 hover:bg-[#1a2035] rounded transition text-[#546e7a]"
            title="Refresh status"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          {status?.connected ? (
            <button
              onClick={handleDisconnect}
              className="bg-[#1a2035] border border-[#ff4757]/30 text-[#ff4757] px-4 py-2 rounded text-sm font-semibold hover:bg-[#ff4757]/10 transition"
            >
              Disconnect
            </button>
          ) : (
            <button
              onClick={handleConnect}
              disabled={!status?.configured || connecting}
              className="bg-[#00d4aa] text-[#0a0e1a] px-4 py-2 rounded text-sm font-semibold flex items-center gap-2 hover:bg-[#00d4aa]/90 transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {connecting ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" /> Connecting...
                </>
              ) : (
                <>
                  <ExternalLink className="w-4 h-4" /> Connect to Zerodha
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {status && !status.installed && (
        <div className="bg-[#ff4757]/10 border border-[#ff4757]/30 rounded p-3 text-xs text-[#ff4757]">
          The <code>kiteconnect</code> package isn't installed on the server. Run{' '}
          <code>pip install kiteconnect</code> in the backend environment.
        </div>
      )}

      {status && status.installed && !status.configured && (
        <div className="bg-[#1a2035] border border-[#1a2035] rounded p-4 space-y-2">
          <p className="text-xs text-[#8892a6]">
            To enable this integration, get an API key + secret from{' '}
            <a
              href="https://developers.kite.trade/"
              target="_blank"
              rel="noreferrer"
              className="text-[#00d4aa] underline"
            >
              developers.kite.trade
            </a>{' '}
            (requires an active Zerodha account + the Kite Connect API subscription), then add
            them to <code className="text-[#e8eaf6]">backend/.env</code>:
          </p>
          <pre className="bg-[#0a0e1a] rounded p-3 text-[11px] text-[#00d4aa] overflow-x-auto">
{`ZERODHA_API_KEY=your_api_key_here
ZERODHA_API_SECRET=your_api_secret_here`}
          </pre>
          <p className="text-xs text-[#546e7a]">
            A template is provided at <code>backend/.env.example</code> — copy it to{' '}
            <code>backend/.env</code> and restart the backend. No code changes needed.
          </p>
        </div>
      )}

      {error && (
        <div className="bg-[#ff4757]/10 border border-[#ff4757]/30 rounded p-3 text-xs text-[#ff4757] flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {status?.message && status.configured && (
        <p className="text-xs text-[#546e7a] flex items-start gap-1.5">
          <Info className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
          {status.message}
        </p>
      )}

      {status?.configured && !status?.connected && (
        <div>
          <button
            onClick={() => setShowManualEntry(!showManualEntry)}
            className="text-xs text-[#546e7a] hover:text-[#00d4aa] underline"
          >
            {showManualEntry ? 'Hide' : "Redirect not landing back here? Paste request_token manually"}
          </button>
          {showManualEntry && (
            <div className="mt-2 bg-[#1a2035] border border-[#1a2035] rounded p-3 space-y-2">
              <p className="text-xs text-[#8892a6]">
                If your Kite Connect app's Redirect URL uses <code>https://</code> and can't reach
                this app (which runs on plain <code>http://localhost:3000</code>), your browser will
                still show the redirected URL in its address bar after you log in — even if the page
                itself fails to load. Copy the value after <code>request_token=</code> from that URL
                and paste it below.
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Paste request_token here"
                  value={manualToken}
                  onChange={(e) => setManualToken(e.target.value)}
                  className="flex-1 bg-[#0a0e1a] border border-[#1a2035] rounded px-3 py-2 text-xs text-[#e8eaf6]"
                />
                <button
                  onClick={handleManualSubmit}
                  disabled={connecting}
                  className="bg-[#00d4aa] text-[#0a0e1a] px-4 py-2 rounded text-xs font-semibold hover:bg-[#00d4aa]/90 transition disabled:opacity-50"
                >
                  {connecting ? 'Submitting...' : 'Submit'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Fully automated login (user ID + password + TOTP secret) ──────── */}
      {status?.configured && (
        <div className="border-t border-[#1a2035] pt-3">
          <div className="flex items-center justify-between">
            <button
              onClick={() => setShowAutoLogin(!showAutoLogin)}
              className="text-xs text-[#546e7a] hover:text-[#00d4aa] underline flex items-center gap-1.5"
            >
              <Key className="w-3.5 h-3.5" />
              {showAutoLogin ? 'Hide' : 'Fully automated login (no manual browser step)'}
            </button>
            {autoLoginStatus?.remembered && (
              <span className="text-[10px] text-[#00d4aa] flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> Remembered for {autoLoginStatus.user_id} — auto-reconnects daily
              </span>
            )}
          </div>

          {showAutoLogin && (
            <div className="mt-2 bg-[#1a2035] border border-[#1a2035] rounded p-4 space-y-3">
              <div className="bg-[#ffa502]/10 border border-[#ffa502]/30 rounded p-3 text-xs text-[#ffa502] space-y-1.5">
                <p className="font-bold flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5" /> How this works — read first
                </p>
                <p>
                  Zerodha's official API has no password login (SEBI requires 2FA via browser, by
                  design). This automates Zerodha's actual login website instead — a well-known
                  pattern in the Indian algo-trading community — using undocumented endpoints that
                  could change without notice. It still goes through 2FA, just automatically via TOTP.
                </p>
                <p>
                  You need your <strong>TOTP secret</strong> (the setup key from when you first
                  enabled 2FA — not the 6-digit code), not your password manager's saved password
                  alone. Storing your password locally is a real security tradeoff — only use this
                  if you're comfortable with that on your own machine.
                </p>
              </div>

              {!autoLoginStatus?.pyotp_available && (
                <div className="bg-[#ff4757]/10 border border-[#ff4757]/30 rounded p-2 text-xs text-[#ff4757]">
                  <code>pyotp</code> not installed on the server. Run <code>pip install pyotp</code>.
                </div>
              )}

              {autoLoginStatus?.remembered ? (
                <div className="flex items-center justify-between">
                  <p className="text-xs text-[#8892a6]">
                    Credentials remembered for <strong>{autoLoginStatus.user_id}</strong>. The
                    background job will auto-reconnect your session daily without you doing anything.
                  </p>
                  <button
                    onClick={handleForgetAutoLogin}
                    className="bg-[#1a2035] border border-[#ff4757]/30 text-[#ff4757] px-3 py-1.5 rounded text-xs font-semibold hover:bg-[#ff4757]/10 transition flex-shrink-0"
                  >
                    Forget
                  </button>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 gap-2">
                    <input
                      type="text"
                      placeholder="Zerodha User ID (e.g. AB1234)"
                      value={autoUserId}
                      onChange={(e) => setAutoUserId(e.target.value)}
                      className="bg-[#0a0e1a] border border-[#1a2035] rounded px-3 py-2 text-xs text-[#e8eaf6]"
                    />
                    <input
                      type="password"
                      placeholder="Zerodha Password"
                      value={autoPassword}
                      onChange={(e) => setAutoPassword(e.target.value)}
                      className="bg-[#0a0e1a] border border-[#1a2035] rounded px-3 py-2 text-xs text-[#e8eaf6]"
                    />
                    <input
                      type="password"
                      placeholder="TOTP Secret (setup key, not the 6-digit code)"
                      value={autoTotpSecret}
                      onChange={(e) => setAutoTotpSecret(e.target.value)}
                      className="bg-[#0a0e1a] border border-[#1a2035] rounded px-3 py-2 text-xs text-[#e8eaf6]"
                    />
                  </div>
                  {autoLoginError && (
                    <p className="text-xs text-[#ff4757]">{autoLoginError}</p>
                  )}
                  <button
                    onClick={handleAutoLoginSubmit}
                    disabled={autoLoginBusy || !autoLoginStatus?.pyotp_available}
                    className="bg-[#00d4aa] text-[#0a0e1a] px-4 py-2 rounded text-xs font-semibold hover:bg-[#00d4aa]/90 transition disabled:opacity-50 w-full"
                  >
                    {autoLoginBusy ? 'Logging in...' : 'Login Automatically & Remember'}
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      )}

      <div className="bg-[#ffa502]/10 border border-[#ffa502]/30 rounded p-3 text-xs text-[#ffa502] flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
        Once connected, order-placement endpoints use REAL money on your actual
        Zerodha account. For risk-free testing, keep using the app's built-in
        "Dry Run" (paper trading) feature instead.
      </div>
    </SectionCard>
  );
}

// ── Dataset Freshness Section ───────────────────────────────────────────────

function DatasetFreshnessSection() {
  const [info, setInfo] = useState(null);
  const [updating, setUpdating] = useState(false);
  const [result, setResult] = useState(null);

  const fetchInfo = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/dataset/status`);
      setInfo(await res.json());
    } catch (e) {
      setInfo(null);
    }
  }, []);

  useEffect(() => {
    fetchInfo();
  }, [fetchInfo]);

  const handleUpdateNow = async () => {
    setUpdating(true);
    setResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/dataset/update-now`, { method: 'POST' });
      const data = await res.json();
      setResult(data);
      await fetchInfo();
    } catch (e) {
      setResult({ error: e.message });
    } finally {
      setUpdating(false);
    }
  };

  return (
    <SectionCard
      icon={Brain}
      title="Model Training Data"
      subtitle="The CAS signal models automatically incorporate newly-completed trading days over time — they don't stay frozen on old data."
    >
      {info ? (
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <p className="text-[10px] text-[#546e7a] uppercase">Training Rows</p>
            <p className="text-[#e8eaf6] font-mono font-bold">{info.master_dataset_v2?.rows ?? info.master_dataset?.rows ?? '—'}</p>
          </div>
          <div>
            <p className="text-[10px] text-[#546e7a] uppercase">Last Trading Day Included</p>
            <p className="text-[#e8eaf6] font-mono font-bold">{info.master_dataset?.last_trading_day ?? '—'}</p>
          </div>
          <div>
            <p className="text-[10px] text-[#546e7a] uppercase">Auto-Check Interval</p>
            <p className="text-[#e8eaf6] font-mono font-bold">Every {info.auto_update_check_interval_hours}h</p>
          </div>
          <div>
            <p className="text-[10px] text-[#546e7a] uppercase">File Last Updated</p>
            <p className="text-[#e8eaf6] font-mono font-bold">
              {info.master_dataset?.file_last_modified
                ? new Date(info.master_dataset.file_last_modified).toLocaleString()
                : '—'}
            </p>
          </div>
        </div>
      ) : (
        <p className="text-xs text-[#546e7a]">Could not reach backend to check dataset status.</p>
      )}

      <button
        onClick={handleUpdateNow}
        disabled={updating}
        className="bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-4 py-2 rounded text-sm flex items-center gap-2 hover:border-[#00d4aa] transition disabled:opacity-50"
      >
        <RefreshCw className={`w-4 h-4 ${updating ? 'animate-spin' : ''}`} />
        {updating ? 'Checking for new data...' : 'Check for new trading days now'}
      </button>

      {result && (
        <div
          className={`rounded p-3 text-xs ${
            result.error
              ? 'bg-[#ff4757]/10 border border-[#ff4757]/30 text-[#ff4757]'
              : 'bg-[#00d4aa]/10 border border-[#00d4aa]/30 text-[#00d4aa]'
          }`}
        >
          {result.error
            ? result.error
            : result.new_rows_added > 0
            ? `✓ Added ${result.new_rows_added} new trading day(s). Models will retrain on the next signal request.`
            : 'No new completed trading days available yet (NSE data typically lags by ~1 day).'}
        </div>
      )}

      <p className="text-xs text-[#546e7a]">
        A background job also runs this check automatically every few hours — you don't need to
        click the button above unless you want an immediate check.
      </p>
    </SectionCard>
  );
}

// ── Auto-Trader Section ─────────────────────────────────────────────────────

function AutoTraderSection() {
  const [status, setStatus] = useState(null);
  const [log, setLog] = useState([]);
  const [showLog, setShowLog] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [confirmText, setConfirmText] = useState('');

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auto-trader/status`);
      setStatus(await res.json());
    } catch (e) {
      setStatus(null);
    }
  }, []);

  const fetchLog = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/auto-trader/log?limit=50`);
      const data = await res.json();
      setLog(data.entries || []);
    } catch (e) {
      setLog([]);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleEnable = async () => {
    if (confirmText !== 'ENABLE') {
      setError('Type ENABLE in the confirmation box to proceed — this places REAL orders with real money.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/auto-trader/enable`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Could not enable');
      setConfirmText('');
      await fetchStatus();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleDisable = async () => {
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/auto-trader/disable`, { method: 'POST' });
      await fetchStatus();
    } finally {
      setBusy(false);
    }
  };

  const updateConfig = async (patch) => {
    try {
      const res = await fetch(`${API_BASE}/api/auto-trader/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Update failed');
      await fetchStatus();
    } catch (e) {
      setError(e.message);
    }
  };

  const toggleLog = async () => {
    if (!showLog) await fetchLog();
    setShowLog(!showLog);
  };

  return (
    <SectionCard
      icon={Bot}
      title="Auto-Trader"
      subtitle="Fully automated trade execution based on the CAS signal — places REAL orders on your connected Zerodha account. Disabled by default."
    >
      {/* Prominent warning banner — always visible regardless of state */}
      <div className="bg-[#ff4757]/10 border-2 border-[#ff4757]/40 rounded-lg p-4 space-y-2">
        <p className="text-sm font-bold text-[#ff4757] flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" /> This trades with REAL money — read before enabling
        </p>
        <ul className="text-xs text-[#ff4757]/90 list-disc list-inside space-y-1">
          <li>By default, only trades the validated high-conviction rule (86.5% historical win rate, BULLISH-only)</li>
          <li>Hard limits: max 1 open position, max 2 trades/day, automatic daily-loss circuit breaker</li>
          <li>Every entry gets an automatic GTT stop-loss + target exit order</li>
          <li><strong>Auto-trading is forced OFF every time the backend restarts</strong> — you must re-enable it explicitly, every session</li>
          <li>Never trades in the last 20 minutes before close (avoids the volatile CAS window itself)</li>
        </ul>
      </div>

      {status ? (
        <>
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3">
              {status.enabled ? (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-[#ff4757]/15 text-[#ff4757] ring-1 ring-[#ff4757]/40 animate-pulse">
                  <Bot className="w-3.5 h-3.5" /> LIVE — TRADING ACTIVE
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-[#546e7a]/15 text-[#546e7a] ring-1 ring-[#546e7a]/30">
                  <XCircle className="w-3.5 h-3.5" /> OFF
                </span>
              )}
              {!status.zerodha_connected && (
                <span className="text-xs text-[#ffa502]">Zerodha not connected — connect above first</span>
              )}
            </div>

            {status.enabled ? (
              <button
                onClick={handleDisable}
                disabled={busy}
                className="bg-[#ff4757] text-white px-5 py-2 rounded text-sm font-bold hover:bg-[#ff4757]/90 transition disabled:opacity-50"
              >
                🛑 STOP AUTO-TRADING
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder="Type ENABLE to confirm"
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  className="bg-[#1a2035] border border-[#ff4757]/30 rounded px-3 py-2 text-xs text-[#e8eaf6] w-40"
                />
                <button
                  onClick={handleEnable}
                  disabled={busy || !status.zerodha_connected}
                  className="bg-[#ff4757]/20 border border-[#ff4757] text-[#ff4757] px-4 py-2 rounded text-sm font-bold hover:bg-[#ff4757]/30 transition disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Enable Auto-Trading
                </button>
              </div>
            )}
          </div>

          {error && (
            <div className="bg-[#ff4757]/10 border border-[#ff4757]/30 rounded p-3 text-xs text-[#ff4757]">
              {error}
            </div>
          )}

          {/* Config */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-[#e8eaf6] mb-1.5 block">Trading Mode</label>
              <select
                value={status.mode}
                onChange={(e) => updateConfig({ mode: e.target.value })}
                className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-sm text-[#e8eaf6]"
              >
                <option value="high_conviction_only">High-Conviction Only (safe, 86.5% win rate)</option>
                <option value="directional_signal">Directional Signal (riskier, ~62% accuracy)</option>
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-[#e8eaf6] mb-1.5 block">Lots per Trade</label>
              <input
                type="number" min="1" max="10"
                value={status.lots}
                onChange={(e) => updateConfig({ lots: Number(e.target.value) })}
                className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-sm text-[#e8eaf6]"
              />
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold text-[#e8eaf6] mb-1.5 block">
              Daily Loss Circuit Breaker: ₹{status.max_daily_loss}
            </label>
            <input
              type="range" min="500" max="10000" step="500"
              value={status.max_daily_loss}
              onChange={(e) => updateConfig({ max_daily_loss: Number(e.target.value) })}
              className="w-full accent-[#ff4757]"
            />
            <p className="text-xs text-[#546e7a] mt-1">
              Auto-trading pauses for the rest of the day if realized losses hit this amount.
            </p>
          </div>

          {/* Live counters */}
          <div className="grid grid-cols-3 gap-4 text-sm bg-[#1a2035] rounded p-3">
            <div>
              <p className="text-[10px] text-[#546e7a] uppercase">Trades Today</p>
              <p className="text-[#e8eaf6] font-mono font-bold">{status.trades_today} / {status.max_trades_per_day}</p>
            </div>
            <div>
              <p className="text-[10px] text-[#546e7a] uppercase">Realized P&L Today</p>
              <p className={`font-mono font-bold ${status.realized_pnl_today >= 0 ? 'text-[#00d4aa]' : 'text-[#ff4757]'}`}>
                ₹{status.realized_pnl_today.toFixed(0)}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-[#546e7a] uppercase">No New Entries After</p>
              <p className="text-[#e8eaf6] font-mono font-bold">{status.no_new_entry_after}</p>
            </div>
          </div>
        </>
      ) : (
        <p className="text-xs text-[#546e7a]">Could not reach backend to check auto-trader status.</p>
      )}

      <button
        onClick={toggleLog}
        className="bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-4 py-2 rounded text-sm flex items-center gap-2 hover:border-[#00d4aa] transition"
      >
        <History className="w-4 h-4" />
        {showLog ? 'Hide' : 'Show'} Audit Log
      </button>

      {showLog && (
        <div className="max-h-80 overflow-y-auto space-y-1.5 bg-[#0a0e1a] rounded p-3">
          {log.length === 0 && <p className="text-xs text-[#546e7a]">No auto-trader activity logged yet.</p>}
          {log.map((entry) => (
            <div key={entry.id} className="text-xs border-b border-[#1a2035] pb-1.5 last:border-0">
              <div className="flex items-center gap-2">
                <span
                  className={`font-mono font-bold ${
                    entry.action === 'TRADE_PLACED'
                      ? 'text-[#00d4aa]'
                      : entry.action === 'ERROR'
                      ? 'text-[#ff4757]'
                      : entry.action === 'KILL_SWITCH'
                      ? 'text-[#ffa502]'
                      : 'text-[#546e7a]'
                  }`}
                >
                  {entry.action}
                </span>
                <span className="text-[#546e7a]">{new Date(entry.timestamp).toLocaleString()}</span>
              </div>
              <p className="text-[#8892a6] mt-0.5">{entry.reason}</p>
              {entry.tradingsymbol && (
                <p className="text-[#546e7a] mt-0.5">
                  {entry.tradingsymbol} × {entry.quantity} @ ₹{entry.entry_price} (SL ₹{entry.sl_price} / Target ₹{entry.target_price})
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      <TodaysTradesSection />
    </SectionCard>
  );
}

// ── Today's Executed Trades (Zerodha fills) ──────────────────────────────────

function TodaysTradesSection() {
  const [trades, setTrades] = useState(null);
  const [show, setShow] = useState(false);
  const [loading, setLoading] = useState(false);

  const fetchTrades = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/zerodha/trades`);
      const json = await res.json();
      setTrades(json.trades || []);
    } catch (e) {
      setTrades([]);
    } finally {
      setLoading(false);
    }
  };

  const toggle = () => {
    if (!show && trades === null) fetchTrades();
    setShow(!show);
  };

  return (
    <div className="space-y-3">
      <button
        onClick={toggle}
        className="bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-4 py-2 rounded text-sm flex items-center gap-2 hover:border-[#00d4aa] transition"
      >
        <History className="w-4 h-4 text-[#00d4aa]" />
        {show ? 'Hide' : 'Show'} Today's Executed Trades
        {loading && <span className="text-[#546e7a] text-xs">(loading…)</span>}
      </button>

      {show && trades !== null && (
        <div className="bg-[#0a0e1a] rounded p-3 max-h-64 overflow-y-auto">
          {trades.length === 0 ? (
            <p className="text-xs text-[#546e7a]">No trades executed today (or Zerodha not connected).</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[#546e7a] border-b border-[#1a2035]">
                  <th className="text-left py-1">Symbol</th>
                  <th className="text-left py-1">Side</th>
                  <th className="text-right py-1">Qty</th>
                  <th className="text-right py-1">Price</th>
                  <th className="text-right py-1">Product</th>
                  <th className="text-right py-1">Time</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <tr key={i} className="border-b border-[#1a2035] last:border-0">
                    <td className="py-1 font-mono font-bold text-[#e8eaf6]">{t.tradingsymbol}</td>
                    <td className={`py-1 font-bold ${t.transaction_type === 'BUY' ? 'text-[#00d4aa]' : 'text-[#ff4757]'}`}>
                      {t.transaction_type}
                    </td>
                    <td className="py-1 text-right font-mono text-[#e8eaf6]">{t.quantity}</td>
                    <td className="py-1 text-right font-mono text-[#e8eaf6]">₹{t.average_price?.toFixed(2)}</td>
                    <td className="py-1 text-right text-[#546e7a]">{t.product}</td>
                    <td className="py-1 text-right text-[#546e7a]">
                      {t.fill_timestamp ? new Date(t.fill_timestamp).toLocaleTimeString() : '—'}
                    </td>
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

// ── Main Settings Page ──────────────────────────────────────────────────────

export default function Settings({ setRefreshInterval }) {
  const [settings, setSettings] = useState(() => {
    try {
      const saved = localStorage.getItem('niftySettings');
      return saved ? { ...DEFAULT_SETTINGS, ...JSON.parse(saved) } : DEFAULT_SETTINGS;
    } catch {
      return DEFAULT_SETTINGS;
    }
  });
  const [saved, setSaved] = useState(false);

  const handleChange = (key, value) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  const handleSave = () => {
    if (setRefreshInterval) setRefreshInterval(settings.refreshMinutes * 60 * 1000);
    localStorage.setItem('niftySettings', JSON.stringify(settings));
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const handleReset = () => {
    if (!window.confirm('Reset all settings to defaults?')) return;
    setSettings(DEFAULT_SETTINGS);
    localStorage.setItem('niftySettings', JSON.stringify(DEFAULT_SETTINGS));
  };

  return (
    <div className="max-w-3xl space-y-6 pb-10">
      <div>
        <h1 className="text-xl font-bold text-[#e8eaf6]">Settings</h1>
        <p className="text-sm text-[#546e7a] mt-1">
          Tune signal behaviour, risk limits, notifications, and broker integration.
        </p>
      </div>

      {/* ── Zerodha Integration ────────────────────────────────────────── */}
      <ZerodhaSection />

      {/* ── Auto-Trader ──────────────────────────────────────────────────── */}
      <AutoTraderSection />

      {/* ── Model Training Data Freshness ───────────────────────────────── */}
      <DatasetFreshnessSection />

      {/* ── Signal & Strategy Tuning ───────────────────────────────────── */}
      <SectionCard
        icon={Sliders}
        title="Signal & Strategy Tuning"
        subtitle="Controls how confident the model needs to be before flagging a signal, and how strikes/SL/targets are calculated."
      >
        <div>
          <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">
            Confidence Threshold: {settings.confidenceThreshold}%
          </label>
          <input
            type="range" min="50" max="90"
            value={settings.confidenceThreshold}
            onChange={(e) => handleChange('confidenceThreshold', Number(e.target.value))}
            className="w-full accent-[#00d4aa]"
          />
          <p className="text-xs text-[#546e7a] mt-1">Minimum confidence required to generate a signal (50-90%)</p>
        </div>

        <div>
          <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">VIX Warning Threshold</label>
          <input
            type="number"
            value={settings.vixMaxThreshold}
            onChange={(e) => handleChange('vixMaxThreshold', Number(e.target.value))}
            className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-[#e8eaf6]"
          />
          <p className="text-xs text-[#546e7a] mt-1">Show warning when VIX exceeds this level (default: 22)</p>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">Default Interval</label>
            <select
              value={settings.interval}
              onChange={(e) => handleChange('interval', e.target.value)}
              className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-[#e8eaf6]"
            >
              <option value="1d">Daily (1D)</option>
              <option value="1h">Hourly (1H)</option>
              <option value="15m">15 Minutes (15M)</option>
            </select>
          </div>
          <div>
            <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">Strike Step (₹)</label>
            <input
              type="number"
              value={settings.strikeStep}
              onChange={(e) => handleChange('strikeStep', Number(e.target.value))}
              className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-[#e8eaf6]"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">
              Stop-Loss (ATR ×): {settings.slMultiplier}x
            </label>
            <input
              type="range" min="0.5" max="3" step="0.1"
              value={settings.slMultiplier}
              onChange={(e) => handleChange('slMultiplier', Number(e.target.value))}
              className="w-full accent-[#ff4757]"
            />
          </div>
          <div>
            <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">
              Target (ATR ×): {settings.targetMultiplier}x
            </label>
            <input
              type="range" min="1" max="5" step="0.1"
              value={settings.targetMultiplier}
              onChange={(e) => handleChange('targetMultiplier', Number(e.target.value))}
              className="w-full accent-[#00d4aa]"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">Max Hold Days</label>
            <input
              type="number" min="1" max="10"
              value={settings.maxHoldDays}
              onChange={(e) => handleChange('maxHoldDays', Number(e.target.value))}
              className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-[#e8eaf6]"
            />
          </div>
          <div>
            <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">Lot Size</label>
            <input
              type="number" min="1"
              value={settings.lotSize}
              onChange={(e) => handleChange('lotSize', Number(e.target.value))}
              className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-[#e8eaf6]"
            />
            <p className="text-xs text-[#546e7a] mt-1">Current Nifty lot size (verify with NSE circulars)</p>
          </div>
        </div>
      </SectionCard>

      {/* ── Risk Management ────────────────────────────────────────────── */}
      <SectionCard
        icon={Shield}
        title="Risk Management"
        subtitle="Guard rails to help limit downside — enforced client-side in the Dry Run and CAS Signal pages."
      >
        <div>
          <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">
            Max Daily Loss: {settings.maxDailyLossPct}% of capital
          </label>
          <input
            type="range" min="1" max="20"
            value={settings.maxDailyLossPct}
            onChange={(e) => handleChange('maxDailyLossPct', Number(e.target.value))}
            className="w-full accent-[#ff4757]"
          />
        </div>
        <div>
          <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">Max Concurrent Open Trades</label>
          <input
            type="number" min="1" max="10"
            value={settings.maxOpenTrades}
            onChange={(e) => handleChange('maxOpenTrades', Number(e.target.value))}
            className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-[#e8eaf6]"
          />
        </div>
        <ToggleRow
          label="Only trade high-conviction signals"
          description="Only act on the validated high-conviction mean-reversion rule (86.5% historical win rate) — ignore lower-confidence signals entirely."
          checked={settings.requireHighConviction}
          onChange={(v) => handleChange('requireHighConviction', v)}
        />
      </SectionCard>

      {/* ── Refresh & Notifications ─────────────────────────────────────── */}
      <SectionCard icon={Bell} title="Refresh & Notifications">
        <ToggleRow
          label="Auto Refresh (Dashboard)"
          checked={settings.autoRefresh}
          onChange={(v) => handleChange('autoRefresh', v)}
        />
        {settings.autoRefresh && (
          <div className="ml-7">
            <label className="text-xs text-[#546e7a] mb-2 block">
              Refresh every {settings.refreshMinutes} minute{settings.refreshMinutes !== 1 ? 's' : ''}
            </label>
            <input
              type="range" min="1" max="30"
              value={settings.refreshMinutes}
              onChange={(e) => handleChange('refreshMinutes', Number(e.target.value))}
              className="w-full accent-[#00d4aa]"
            />
          </div>
        )}

        <div>
          <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">
            CAS Signal Auto-Refresh: every {settings.casAutoRefreshSeconds}s
          </label>
          <input
            type="range" min="10" max="60" step="5"
            value={settings.casAutoRefreshSeconds}
            onChange={(e) => handleChange('casAutoRefreshSeconds', Number(e.target.value))}
            className="w-full accent-[#00d4aa]"
          />
        </div>

        <ToggleRow
          label="Browser Notifications"
          description="Notify when a new high-confidence or high-conviction signal appears (requires browser permission)."
          checked={settings.notifications}
          onChange={(v) => handleChange('notifications', v)}
        />
        <ToggleRow
          label="Sound Alerts"
          description="Play a short sound alongside notifications."
          checked={settings.soundAlerts}
          onChange={(v) => handleChange('soundAlerts', v)}
        />
      </SectionCard>

      {/* ── Display ──────────────────────────────────────────────────────── */}
      <SectionCard icon={Palette} title="Display">
        <div>
          <label className="text-sm font-semibold text-[#e8eaf6] mb-2 block">Theme</label>
          <select
            value={settings.theme}
            onChange={(e) => handleChange('theme', e.target.value)}
            className="w-full bg-[#1a2035] border border-[#1a2035] rounded px-3 py-2 text-[#e8eaf6]"
          >
            <option value="dark">Dark (default)</option>
            <option value="darker">Darker (higher contrast)</option>
          </select>
          <p className="text-xs text-[#546e7a] mt-1">Theme switching is cosmetic-only in this version.</p>
        </div>
        <ToggleRow
          label="Compact Mode"
          description="Reduce padding/spacing across pages to fit more on screen."
          checked={settings.compactMode}
          onChange={(v) => handleChange('compactMode', v)}
        />
        <ToggleRow
          label="Show Option Greeks"
          description="Display Delta/Gamma/Theta/Vega estimates where available (Options Chain page)."
          checked={settings.showGreeks}
          onChange={(v) => handleChange('showGreeks', v)}
        />
      </SectionCard>

      {/* ── Data & Storage ──────────────────────────────────────────────── */}
      <SectionCard icon={Database} title="Data & Storage" subtitle="Manage locally cached data.">
        <div className="flex flex-wrap gap-3">
          <button
            onClick={async () => {
              await fetch(`${API_BASE}/api/backtest/cache`, { method: 'DELETE' });
              alert('Backtest cache cleared.');
            }}
            className="bg-[#1a2035] border border-[#1a2035] text-[#e8eaf6] px-4 py-2 rounded text-sm hover:border-[#00d4aa] transition"
          >
            Clear Backtest Cache
          </button>
          <button
            onClick={() => {
              if (window.confirm('Delete ALL paper (dry-run) trades? This cannot be undone.')) {
                fetch(`${API_BASE}/api/dry-run/trades`, { method: 'DELETE' }).then(() =>
                  alert('All dry-run trades cleared.')
                );
              }
            }}
            className="bg-[#1a2035] border border-[#ff4757]/30 text-[#ff4757] px-4 py-2 rounded text-sm hover:bg-[#ff4757]/10 transition"
          >
            Clear Dry-Run Trades
          </button>
        </div>
      </SectionCard>

      {/* ── Save / Reset ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          className="bg-[#00d4aa] text-[#0a0e1a] px-6 py-2.5 rounded font-semibold flex items-center gap-2 hover:bg-[#00d4aa]/90 transition"
        >
          <Save className="w-4 h-4" />
          Save Settings
        </button>
        <button
          onClick={handleReset}
          className="text-[#546e7a] hover:text-[#e8eaf6] px-4 py-2.5 text-sm transition"
        >
          Reset to defaults
        </button>
        {saved && (
          <span className="text-[#00d4aa] text-sm font-semibold flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4" /> Saved!
          </span>
        )}
      </div>

      {/* ── Disclaimer ───────────────────────────────────────────────────── */}
      <div className="bg-[#ff4757]/10 border border-[#ff4757] rounded-lg p-4">
        <p className="text-xs text-[#ff4757] leading-relaxed">
          ⚠️ <strong>Disclaimer:</strong> This is an educational tool only. It is not SEBI-registered
          advice. Options trading involves substantial risk of loss. Trade only with capital you can
          afford to lose. Past performance does not guarantee future results. If you connect a real
          Zerodha account, order placement uses REAL money — always test extensively with the Dry Run
          feature first.
        </p>
      </div>
    </div>
  );
}
