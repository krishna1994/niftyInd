import React from 'react';

export default function IndicatorBoard({ indicators, expanded, onToggle }) {
  if (!indicators) return null;

  const getSignalBadge = (indicator) => {
    if (indicator.signal === 'BEAR') return '🔴 BEAR';
    if (indicator.signal === 'BULL') return '🟢 BULL';
    return '⚪ NEUTRAL';
  };

  const getSignalColor = (sig) => {
    if (sig === 'BEAR') return 'bg-[#ff4757]/20 text-[#ff4757]';
    if (sig === 'BULL') return 'bg-[#00d4aa]/20 text-[#00d4aa]';
    return 'bg-[#ffa502]/20 text-[#ffa502]';
  };

  const indicatorList = Object.entries(indicators).filter(([key]) => key !== 'signal');

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
      <h2 className="text-lg font-bold text-[#e8eaf6] mb-4">Indicator Scorecard (10/10)</h2>
      
      <div className="space-y-3">
        {indicatorList.map(([key, indicator]) => (
          <div 
            key={key}
            className="border border-[#1a2035] rounded p-3 hover:bg-[#1a2035] transition cursor-pointer"
            onClick={() => onToggle(expanded === key ? null : key)}
          >
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-semibold text-[#e8eaf6] capitalize">{key}</span>
                  <span className={`text-xs px-2 py-1 rounded ${getSignalColor(indicator.signal || 'NEUTRAL')}`}>
                    {getSignalBadge(indicator)}
                  </span>
                </div>
                <p className="text-xs text-[#546e7a]">{indicator.label}</p>
              </div>

              <div className="flex items-center gap-4">
                {indicator.value !== undefined && (
                  <div className="text-right">
                    <p className="text-sm font-mono font-bold text-[#e8eaf6]">
                      {typeof indicator.value === 'number' ? indicator.value.toFixed(1) : indicator.value}
                    </p>
                  </div>
                )}

                {/* Score bar */}
                <div className="w-12 h-2 bg-[#1a2035] rounded overflow-hidden">
                  <div 
                    className={`h-full ${
                      indicator.signal === 'BULL' ? 'bg-[#00d4aa]' :
                      indicator.signal === 'BEAR' ? 'bg-[#ff4757]' :
                      'bg-[#ffa502]'
                    }`}
                    style={{width: `${(indicator.score || 0) * 100}%`}}
                  />
                </div>
              </div>
            </div>

            {/* Expandable details */}
            {expanded === key && (
              <div className="mt-2 pt-2 border-t border-[#1a2035] text-xs text-[#546e7a] space-y-1">
                {Object.entries(indicator).map(([k, v]) => 
                  !['label', 'signal', 'score'].includes(k) && (
                    <div key={k} className="flex justify-between">
                      <span>{k}:</span>
                      <span className="font-mono">{typeof v === 'number' ? v.toFixed(2) : v}</span>
                    </div>
                  )
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
