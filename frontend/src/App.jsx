import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Navbar from './components/layout/Navbar';
import StatusBar from './components/layout/StatusBar';
import Dashboard from './pages/Dashboard';
import Charts from './pages/Charts';
import Backtest from './pages/Backtest';
import DryRun from './pages/DryRun';
import Settings from './pages/Settings';
import OptionsChain from './pages/OptionsChain';
import CASSignal from './pages/CASSignal';
import IronCondor from './pages/IronCondor';
import Watchlist from './pages/Watchlist';
import Etoro from './pages/Etoro';
import GlobalPortfolio from './pages/GlobalPortfolio';
import IBKROptionStrategy from './pages/IBKROptionStrategy';

function App() {
  const [signalData, setSignalData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(300000); // 5 minutes

  useEffect(() => {
    const fetchSignal = async () => {
      try {
        const response = await fetch('http://localhost:8001/api/signal');
        const data = await response.json();
        // If backend returned an error object, don't set it as signalData
        if (data.error || !data.signal) {
          console.error('Backend error:', data.error || 'Invalid response', data.message || '');
          setLoading(false);
          return;
        }
        setSignalData(data);
        setLoading(false);
      } catch (error) {
        console.error('Error fetching signal:', error);
        setLoading(false);
      }
    };

    fetchSignal();
    const interval = setInterval(fetchSignal, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval]);

  return (
    <Router>
      <div className="min-h-screen bg-[#0a0e1a]">
        <StatusBar signalData={signalData} loading={loading} />
        <Navbar />
        
        <main className="container mx-auto px-4 py-6">
          <Routes>
            <Route path="/" element={<Dashboard signalData={signalData} loading={loading} />} />
            <Route path="/cas-signal" element={<CASSignal />} />
            <Route path="/options" element={<OptionsChain />} />
            <Route path="/charts" element={<Charts signalData={signalData} loading={loading} />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/etoro" element={<Etoro />} />
            <Route path="/global-portfolio" element={<GlobalPortfolio />} />
            <Route path="/ibkr-strategy" element={<IBKROptionStrategy />} />
            <Route path="/backtest" element={<Backtest />} />
            <Route path="/dry-run" element={<DryRun />} />
            <Route path="/iron-condor" element={<IronCondor />} />
            <Route path="/settings" element={<Settings setRefreshInterval={setRefreshInterval} />} />
          </Routes>
        </main>

        {/* Footer disclaimer */}
        <footer className="border-t border-[#1a2035] mt-12 py-4 text-center text-xs text-[#546e7a]">
          <p>⚠️ Educational tool only. Not SEBI-registered advice. Trade at your own risk.</p>
        </footer>
      </div>
    </Router>
  );
}

export default App;
