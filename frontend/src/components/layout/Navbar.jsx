import React, { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { TrendingUp, Zap, Settings, ChevronDown } from 'lucide-react';

const NAV_GROUPS = [
  {
    label: 'Core',
    links: [
      { to: '/', label: 'Dashboard' },
      { to: '/global-portfolio', label: 'Global Portfolio', highlight: true },
    ]
  },
  {
    label: 'Analysis',
    links: [
      { to: '/cas-signal', label: 'CAS Signal', highlight: true },
      { to: '/charts', label: 'Charts' },
      { to: '/watchlist', label: 'Watchlist' },
      { to: '/options', label: 'Options Chain' },
    ]
  },
  {
    label: 'Trading',
    links: [
      { to: '/ibkr-strategy', label: 'IBKR Strategy', highlight: true },
      { to: '/iron-condor', label: 'Iron Condor' },
      { to: '/dry-run', label: 'Dry Run' },
      { to: '/backtest', label: 'Backtest' },
    ]
  }
];

export default function Navbar() {
  const location = useLocation();
  const [openGroup, setOpenGroup] = useState(null);

  return (
    <nav className="border-b border-[#1a2035] sticky top-0 z-50 bg-[#0a0e1a]/95 backdrop-blur">
      <div className="container mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-6 h-6 text-[#00d4aa]" />
          <h1 className="text-xl font-bold text-[#e8eaf6] tracking-tight">Nifty Signal</h1>
        </div>

        <div className="flex items-center gap-2 text-sm">
          {NAV_GROUPS.map((group) => (
            <div key={group.label} className="relative">
              <button
                onClick={() => setOpenGroup(openGroup === group.label ? null : group.label)}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-[#546e7a] hover:text-white transition-colors font-medium"
              >
                {group.label}
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${openGroup === group.label ? 'rotate-180' : ''}`} />
              </button>

              {openGroup === group.label && (
                <>
                  {/* Backdrop to close on outside click */}
                  <div className="fixed inset-0 z-40" onClick={() => setOpenGroup(null)} />
                  <div className="absolute top-full right-0 mt-2 w-48 bg-[#111827] border border-white/10 rounded-xl shadow-2xl py-2 z-50">
                    {group.links.map(({ to, label, highlight }) => {
                      const isActive = location.pathname === to;
                      return (
                        <Link
                          key={to}
                          to={to}
                          onClick={() => setOpenGroup(null)}
                          className={`flex items-center justify-between px-4 py-2.5 transition-colors text-sm ${
                            isActive
                              ? 'text-[#00d4aa] bg-[#00d4aa]/10 font-semibold'
                              : 'text-white/60 hover:text-white hover:bg-white/5'
                          }`}
                        >
                          {label}
                          {highlight && !isActive && <Zap className="w-3 h-3 text-[#ffa502]" />}
                        </Link>
                      );
                    })}
                  </div>
                </>
              )}
            </div>
          ))}

          <div className="h-5 w-px bg-white/10 mx-1" />

          <Link
            to="/settings"
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition ${
              location.pathname === '/settings'
                ? 'text-[#00d4aa] bg-[#00d4aa]/10 font-semibold'
                : 'text-[#546e7a] hover:text-white hover:bg-white/5'
            }`}
          >
            <Settings className="w-4 h-4" />
            Settings
          </Link>
        </div>
      </div>
    </nav>
  );
}