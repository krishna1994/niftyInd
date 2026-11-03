import React from 'react';
import { AlertTriangle, ShieldAlert, Shield } from 'lucide-react';

export default function VixWarning({ vix, regime, penalty, message }) {
  // Determine styling based on regime
  const config = {
    EXTREME: {
      bg: 'bg-[#ff4757]/15',
      border: 'border-[#ff4757]',
      color: '#ff4757',
      icon: <ShieldAlert className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: '#ff4757' }} />,
      title: '⛔ Extreme VIX — Signals Suppressed',
      advice: 'VIX above 28 means extreme fear in the market. Option premiums are very expensive and moves are unpredictable. The signal confidence has been reduced by 20%. Strongly consider staying out.',
    },
    HIGH: {
      bg: 'bg-[#ff4757]/10',
      border: 'border-[#ff4757]',
      color: '#ff4757',
      icon: <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: '#ff4757' }} />,
      title: '⚠️ High VIX — Elevated Premiums',
      advice: 'VIX above 22 means premiums are expensive. You are paying more for the same option. Signal confidence reduced by 10%. Trade smaller size or wait for VIX to cool below 20.',
    },
    ELEVATED: {
      bg: 'bg-[#ffa502]/10',
      border: 'border-[#ffa502]',
      color: '#ffa502',
      icon: <AlertTriangle className="w-5 h-5 flex-shrink-0 mt-0.5" style={{ color: '#ffa502' }} />,
      title: '⚡ Elevated VIX — Use Caution',
      advice: 'VIX above 20 indicates above-average volatility. Signal confidence reduced by 5%. Consider tighter stop-losses.',
    },
  };

  const c = config[regime] || config['HIGH'];

  return (
    <div className={`${c.bg} border-l-4 ${c.border} p-4 rounded`}>
      <div className="flex gap-3">
        {c.icon}
        <div className="flex-1">
          <div className="flex items-center justify-between">
            <p className="font-semibold text-sm" style={{ color: c.color }}>{c.title}</p>
            <div className="flex items-center gap-3 text-xs font-mono">
              <span style={{ color: c.color }}>
                VIX: <strong>{vix?.toFixed(2)}</strong>
              </span>
              {penalty > 0 && (
                <span className="bg-[#ff4757]/20 text-[#ff4757] px-2 py-0.5 rounded">
                  -{penalty}% confidence
                </span>
              )}
            </div>
          </div>
          <p className="text-xs mt-1" style={{ color: `${c.color}99` }}>
            {c.advice}
          </p>
          <div className="mt-2 flex gap-4 text-xs text-[#546e7a]">
            <span>Normal: &lt;15</span>
            <span className="text-[#ffa502]">Caution: 15–20</span>
            <span className="text-[#ff7675]">High: 20–28</span>
            <span className="text-[#ff4757]">Extreme: &gt;28</span>
          </div>
        </div>
      </div>
    </div>
  );
}
