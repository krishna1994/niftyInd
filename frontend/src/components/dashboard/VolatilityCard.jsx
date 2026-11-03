import React, { useState, useEffect } from 'react';
import { Zap, TrendingUp, AlertCircle, Activity } from 'lucide-react';

const API_BASE = "http://localhost:8001";

const VolatilityCard = () => {
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchVol = async () => {
        try {
            const res = await fetch(`${API_BASE}/api/volatility/analysis`);
            const json = await res.json();
            setData(json);
        } catch (e) {
            console.error("Volatility fetch failed", e);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchVol();
        const interval = setInterval(fetchVol, 60000);
        return () => clearInterval(interval);
    }, []);

    if (loading) return <div className="p-4 text-gray-400 animate-pulse">Loading Volatility...</div>;
    if (!data || data.error) return null;

    const regime = data.volatility_regime;
    const isExpensive = regime.regime.includes("EXPENSIVE") || regime.regime.includes("HIGH");
    const isCheap = regime.regime.includes("CHEAP") || regime.regime.includes("DEPRESSED");

    return (
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-800 bg-slate-900/50 flex justify-between items-center">
                <div className="flex items-center space-x-2">
                    <Activity className="w-4 h-4 text-indigo-400" />
                    <h3 className="text-slate-200 text-sm font-bold">Volatility Intelligence</h3>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase ${
                    isExpensive ? 'bg-red-900/30 text-red-400' : isCheap ? 'bg-green-900/30 text-green-400' : 'bg-slate-800 text-slate-400'
                }`}>
                    {regime.regime.replace(/_/g, ' ')}
                </span>
            </div>

            <div className="p-4 grid grid-cols-2 gap-3">
                <div className="bg-slate-800/40 p-3 rounded-lg border border-slate-700/50">
                    <div className="text-slate-500 text-[10px] uppercase font-bold mb-1">IV Rank</div>
                    <div className="text-xl font-mono text-slate-200">{data.iv_rank}%</div>
                </div>
                <div className="bg-slate-800/40 p-3 rounded-lg border border-slate-700/50">
                    <div className="text-slate-500 text-[10px] uppercase font-bold mb-1">VRP (IV-RV)</div>
                    <div className={`text-xl font-mono ${data.vrp > 5 ? 'text-red-400' : data.vrp < -5 ? 'text-green-400' : 'text-slate-200'}`}>
                        {data.vrp > 0 ? `+${data.vrp}` : data.vrp}
                    </div>
                </div>
                <div className="bg-slate-800/40 p-3 rounded-lg border border-slate-700/50">
                    <div className="text-slate-500 text-[10px] uppercase font-bold mb-1">IV Percentile</div>
                    <div className="text-xl font-mono text-slate-200">{data.iv_percentile}%</div>
                </div>
                <div className="bg-slate-800/40 p-3 rounded-lg border border-slate-700/50">
                    <div className="text-slate-500 text-[10px] uppercase font-bold mb-1">Current IV</div>
                    <div className="text-xl font-mono text-slate-200">{data.current_iv}%</div>
                </div>
            </div>

            <div className="px-4 pb-4">
                <div className={`p-3 rounded-lg border ${isExpensive ? 'bg-red-900/10 border-red-500/30' : isCheap ? 'bg-green-900/10 border-green-500/30' : 'bg-slate-800/30 border-slate-700'}`}>
                    <div className={`flex items-center text-xs font-bold uppercase mb-1 ${isExpensive ? 'text-red-400' : isCheap ? 'text-green-400' : 'text-slate-400'}`}>
                        <Zap className="w-3 h-3 mr-2" /> Trading Recommendation
                    </div>
                    <div className="text-slate-200 text-sm font-medium">{regime.recommendation}</div>
                    <div className="text-[10px] text-slate-500 mt-1">Confidence: {regime.confidence}</div>
                </div>
            </div>
        </div>
    );
};

export default VolatilityCard;