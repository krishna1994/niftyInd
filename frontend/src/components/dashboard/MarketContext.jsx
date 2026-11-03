import React from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';

export default function MarketContext() {
  // Placeholder data
  const context = {
    trend: 'DOWNTREND',
    support: [22900, 22500],
    resistance: [23600, 24000],
    expiryDays: 3,
    expiryDate: 'Tuesday, April 1'
  };

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
      <h3 className="text-lg font-bold text-[#e8eaf6] mb-4">Market Context</h3>

      <div className="space-y-4">
        <div>
          <p className="text-xs text-[#546e7a] mb-1">Trend Status</p>
          <div className="flex items-center gap-2">
            {context.trend === 'UPTREND' ? (
              <>
                <TrendingUp className="w-4 h-4 text-[#00d4aa]" />
                <span className="font-semibold text-[#00d4aa]">Uptrend</span>
              </>
            ) : context.trend === 'DOWNTREND' ? (
              <>
                <TrendingDown className="w-4 h-4 text-[#ff4757]" />
                <span className="font-semibold text-[#ff4757]">Downtrend</span>
              </>
            ) : (
              <span className="font-semibold text-[#ffa502]">Sideways</span>
            )}
          </div>
        </div>

        <div>
          <p className="text-xs text-[#546e7a] mb-1">Support Levels</p>
          <div className="space-y-1">
            {context.support.map((level, i) => (
              <p key={i} className="text-sm font-mono text-[#ff4757]">{level.toLocaleString()}</p>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs text-[#546e7a] mb-1">Resistance Levels</p>
          <div className="space-y-1">
            {context.resistance.map((level, i) => (
              <p key={i} className="text-sm font-mono text-[#00d4aa]">{level.toLocaleString()}</p>
            ))}
          </div>
        </div>

        <hr className="border-[#1a2035]" />

        <div>
          <p className="text-xs text-[#546e7a] mb-1">Weekly Expiry</p>
          <p className="text-sm font-bold text-[#e8eaf6]">{context.expiryDate}</p>
          <p className="text-xs text-[#ffa502]">Next expiry in {context.expiryDays} days</p>
        </div>
      </div>
    </div>
  );
}
