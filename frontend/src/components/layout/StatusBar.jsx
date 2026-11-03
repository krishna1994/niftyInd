import React, { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';

export default function StatusBar({ signalData, loading }) {
  const [lastUpdated, setLastUpdated] = useState(new Date());
  const [autoRefresh, setAutoRefresh] = useState(true);

  useEffect(() => {
    if (signalData) {
      setLastUpdated(new Date());
    }
  }, [signalData]);

  const getVixColor = (vix) => {
    if (vix < 15) return 'text-[#00d4aa]';
    if (vix < 20) return 'text-[#ffa502]';
    return 'text-[#ff4757]';
  };

  return (
    <div className="bg-[#0f1629] border-b border-[#1a2035] px-4 py-3">
      <div className="container mx-auto flex items-center justify-between">
        <div className="flex items-center gap-8">
          <div>
            <p className="text-xs text-[#546e7a]">NIFTY 50</p>
            <p className="text-2xl font-bold font-mono text-[#e8eaf6]">
              {loading ? '—' : signalData?.spot?.toLocaleString('en-IN', {maximumFractionDigits: 2})}
            </p>
          </div>
          
          <div>
            <p className="text-xs text-[#546e7a]">INDIA VIX</p>
            <p className={`text-lg font-mono font-bold ${getVixColor(signalData?.vix || 15)}`}>
              {loading ? '—' : signalData?.vix?.toFixed(2)}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-xs text-[#546e7a]">Last Updated</p>
            <p className="text-sm font-mono text-[#e8eaf6]">
              {lastUpdated.toLocaleTimeString()}
            </p>
          </div>

          <button
            onClick={() => window.location.reload()}
            className="p-2 hover:bg-[#1a2035] rounded transition text-[#00d4aa]"
          >
            <RefreshCw className="w-4 h-4" />
          </button>

          <label className="flex items-center gap-2 text-xs text-[#546e7a] cursor-pointer">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="w-3 h-3"
            />
            Auto refresh
          </label>
        </div>
      </div>
    </div>
  );
}
