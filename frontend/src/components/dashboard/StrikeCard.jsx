import React from 'react';
import { Target, AlertCircle } from 'lucide-react';

export default function StrikeCard({ strikes, signal }) {
  if (!strikes) return null;

  return (
    <div className="bg-[#0f1629] border border-[#1a2035] rounded-lg p-6">
      <h3 className="text-lg font-bold text-[#e8eaf6] mb-4">Strike Suggestion</h3>

      <div className="space-y-3">
        <div>
          <p className="text-xs text-[#546e7a] mb-1">Recommended</p>
          <p className="text-xl font-bold text-[#00d4aa]">{strikes.recommended}</p>
        </div>

        <div>
          <p className="text-xs text-[#546e7a] mb-1">ATM</p>
          <p className="text-sm font-mono text-[#e8eaf6]">{strikes.atm}</p>
        </div>

        <div>
          <p className="text-xs text-[#546e7a] mb-1">Aggressive</p>
          <p className="text-sm font-mono text-[#ff4757]">{strikes.aggressive}</p>
        </div>

        <hr className="border-[#1a2035] my-4" />

        <div>
          <p className="text-xs text-[#546e7a] mb-1">Stop Loss Level</p>
          <p className="text-sm font-bold font-mono text-[#e8eaf6]">
            {strikes.stop_loss_level?.toFixed(0)}
          </p>
        </div>

        <div>
          <p className="text-xs text-[#546e7a] mb-1">Target 1</p>
          <p className="text-sm font-bold font-mono text-[#00d4aa]">
            {strikes.target_1?.toFixed(0)}
          </p>
        </div>

        <div>
          <p className="text-xs text-[#546e7a] mb-1">Target 2</p>
          <p className="text-sm font-bold font-mono text-[#00d4aa]">
            {strikes.target_2?.toFixed(0)}
          </p>
        </div>
      </div>

      <div className="mt-4 p-2 bg-[#ffa502]/10 border border-[#ffa502]/30 rounded text-xs text-[#ffa502]">
        <p>💡 Exit by Monday EOD to avoid theta decay on weekly options</p>
      </div>
    </div>
  );
}
