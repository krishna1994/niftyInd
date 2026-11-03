import React from 'react';

export default function SignalCard({ signal, confidence = 0, bullConfidence = 0, bearConfidence = 0 }) {
  const getSignalColor = (sig) => {
    switch(sig) {
      case 'BUY CE': return 'text-[#00d4aa] bg-[#00d4aa]/10 border-[#00d4aa]';
      case 'BUY PE': return 'text-[#ff4757] bg-[#ff4757]/10 border-[#ff4757]';
      default: return 'text-[#ffa502] bg-[#ffa502]/10 border-[#ffa502]';
    }
  };

  const getSignalIcon = (sig) => {
    if (sig === 'BUY CE') return '📈';
    if (sig === 'BUY PE') return '📉';
    return '⏸️';
  };

  return (
    <div className={`border-2 rounded-lg p-8 ${getSignalColor(signal)}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wider text-[#546e7a] mb-2">Signal</p>
          <p className="text-5xl font-bold mb-4">{getSignalIcon(signal)} {signal}</p>
          <p className="text-sm text-[#546e7a]">
            {bullConfidence.toFixed(1)}% Bull | {bearConfidence.toFixed(1)}% Bear
          </p>
        </div>

        <div className="text-right">
          <p className="text-xs uppercase text-[#546e7a] mb-2">Confidence</p>
          <div className="text-5xl font-bold font-mono">{confidence.toFixed(1)}%</div>
          <p className="text-xs text-[#546e7a] mt-2">
            {confidence >= 75 ? '🟢 High' : confidence >= 65 ? '🟡 Moderate' : '🔴 Low'}
          </p>
        </div>
      </div>

      {/* Confidence bars */}
      <div className="mt-6 space-y-2">
        <div className="flex gap-2">
          <span className="text-xs text-[#546e7a] w-12">Bull</span>
          <div className="flex-1 h-2 bg-[#1a2035] rounded overflow-hidden">
            <div 
              className="h-full bg-[#00d4aa]" 
              style={{width: `${bullConfidence}%`}}
            />
          </div>
          <span className="text-xs text-[#546e7a] w-12 text-right">{bullConfidence.toFixed(0)}%</span>
        </div>
        <div className="flex gap-2">
          <span className="text-xs text-[#546e7a] w-12">Bear</span>
          <div className="flex-1 h-2 bg-[#1a2035] rounded overflow-hidden">
            <div 
              className="h-full bg-[#ff4757]" 
              style={{width: `${bearConfidence}%`}}
            />
          </div>
          <span className="text-xs text-[#546e7a] w-12 text-right">{bearConfidence.toFixed(0)}%</span>
        </div>
      </div>
    </div>
  );
}
