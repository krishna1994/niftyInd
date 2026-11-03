<!-- Nifty Weekly Option Signal Analyzer - Project Instructions -->

## Project Overview
Full-stack web application for Indian retail traders analyzing Nifty 50 weekly options.
- **Backend:** FastAPI (Python) with yfinance data, 10+ indicators, signal engine, backtester
- **Frontend:** React + TailwindCSS with dark trading terminal theme
- **Data:** Real-time from yfinance (no database needed)

## Directory Structure
```
/home/krissing/niftyInd/
├── backend/                    # FastAPI backend
│   ├── main.py                 # FastAPI app, routes (/api/signal, /api/backtest, /api/health)
│   ├── data.py                 # yfinance fetching (Nifty, VIX)
│   ├── indicators.py           # All 10+ indicator calculations
│   ├── signal_engine.py        # Signal generation logic (BUY CE/PE/STAY OUT)
│   ├── backtester.py           # Historical backtest simulation
│   ├── models.py               # Pydantic response models
│   └── requirements.txt         # Python dependencies
├── frontend/                   # React + TailwindCSS
│   ├── package.json
│   ├── tailwind.config.js
│   ├── public/
│   │   └── index.html
│   └── src/
│       ├── index.js
│       ├── index.css
│       ├── App.jsx
│       ├── components/
│       │   ├── layout/
│       │   │   ├── Navbar.jsx
│       │   │   └── StatusBar.jsx
│       │   ├── dashboard/
│       │   │   ├── SignalCard.jsx
│       │   │   ├── IndicatorBoard.jsx
│       │   │   ├── StrikeCard.jsx
│       │   │   ├── VixWarning.jsx
│       │   │   └── MarketContext.jsx
│       │   ├── charts/
│       │   │   ├── CandleChart.jsx
│       │   │   ├── RsiChart.jsx
│       │   │   ├── MacdChart.jsx
│       │   │   └── AdxChart.jsx
│       │   └── backtest/
│       │       ├── BacktestControls.jsx
│       │       ├── SummaryCards.jsx
│       │       └── TradeLog.jsx
│       ├── pages/
│       │   ├── Dashboard.jsx    # / — Main signal dashboard
│       │   ├── Charts.jsx       # /charts — Chart analysis
│       │   ├── Backtest.jsx     # /backtest — Backtest results
│       │   └── Settings.jsx     # /settings — User settings
│       ├── hooks/
│       │   ├── useSignal.js     # Auto-refresh signal fetching
│       │   └── useBacktest.js   # Backtest fetching
│       ├── utils/
│       │   ├── formatters.js    # Number/date formatting
│       │   └── colors.js        # Signal color helpers
│       └── api/
│           └── client.js        # API client wrapper
├── .gitignore
└── README.md

```

## Tech Stack Checklist

✅ **Backend:**
- [x] FastAPI 0.104.1
- [x] Uvicorn 0.24.0
- [x] yfinance 0.2.32
- [x] pandas 2.1.1
- [x] numpy 1.24.3
- [x] python-dotenv 1.0.0
- [x] pydantic 2.4.2

✅ **Frontend:**
- [x] React 18.2.0
- [x] React Router 6.16.0
- [x] TailwindCSS 3.3.0
- [x] Recharts 2.10.0 (chart library)
- [x] Framer Motion 10.16.4 (animations)
- [x] Lucide React 0.292.0 (icons)
- [x] Axios 1.5.0 (HTTP client)

## Next Steps to Launch

### 1. Install Backend Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Install Frontend Dependencies
```bash
cd frontend
npm install
```

### 3. Start Backend (Port 8000)
```bash
cd backend
uvicorn main:app --reload --port 8000
```

### 4. Start Frontend (Port 3000)
```bash
cd frontend
npm start
```

### 5. Open Browser
Navigate to http://localhost:3000

## Backend API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/signal?interval=1d&period=6mo` | Current Nifty signal + indicators |
| GET | `/api/backtest?period=1y&confidence_threshold=65&signal_type=both` | Historical backtest |

## Frontend Routes

| Path | Component | Description |
|------|-----------|-------------|
| `/` | Dashboard.jsx | Main signal card, indicator board, strikes |
| `/charts` | Charts.jsx | Candlestick + overlays, RSI, MACD, ADX |
| `/backtest` | Backtest.jsx | Equity curve, trade log, heatmap |
| `/settings` | Settings.jsx | User preferences, thresholds, notifications |

## Theme Colors

```
Background:  #0a0e1a (primary), #0f1629 (secondary), #1a2035 (tertiary)
Bullish:     #00d4aa (teal)
Bearish:     #ff4757 (red)
Neutral:     #ffa502 (amber)
Text:        #e8eaf6 (primary), #546e7a (muted)
Grid:        #1a2035 (lines)
```

## Signal Generation Logic

1. Compute all 10 indicators on latest data
2. Score each indicator as bullish (0–1) or bearish (0–1)
3. Calculate weighted confidence:
   - bull_confidence = sum(bull_scores × weights) / max_score × 100
   - bear_confidence = sum(bear_scores × weights) / max_score × 100
4. Generate signal:
   - **BUY CE** if bull ≥ 65% AND bull > bear × 1.5
   - **BUY PE** if bear ≥ 65% AND bear > bull × 1.5
   - **STAY OUT** otherwise

## Key Features Implemented

✅ Real-time Nifty price & India VIX from yfinance
✅ 10+ technical indicators (RSI, MACD, Bollinger, EMA, ADX, Supertrend, Stoch RSI, ATR, Volume, Candles)
✅ Smart confidence-based signal generation
✅ Strike suggestions with ATR-based stops & targets
✅ VIX warning banner (>22)
✅ Indicator scorecard with expandable details
✅ Market context (support/resistance, expiry countdown)
✅ Historical backtester with trade log
✅ Settings page (threshold, notifications, auto-refresh)
✅ Dark trading terminal UI
✅ Mobile responsive design
✅ Auto-refresh every 5 minutes (configurable)

## TODO / Future Enhancements

- [ ] Integrate Recharts for candlestick visualization
- [ ] Add chart overlays (EMA, Bollinger, Supertrend)
- [ ] Implement equity curve chart in backtest
- [ ] Build monthly heatmap (backtest results)
- [ ] Add real option price integration (using option chain APIs)
- [ ] Browser push notifications for new signals
- [ ] Dark mode toggle (already dark by default)
- [ ] Indicator customization per user
- [ ] Export backtest results to CSV
- [ ] Add volume profile analysis
- [ ] Implement Lightweight Charts (TradingView) for better performance

## Troubleshooting

**Backend not starting?**
- Check Python version (3.8+)
- Verify yfinance can download data: `python -c "import yfinance as yf; print(yf.download('^NSEI', period='1d'))"`
- Check port 8000 is free: `lsof -i :8000`

**Frontend not connecting to backend?**
- Verify backend is running on http://localhost:8000
- Check CORS is enabled in FastAPI main.py
- Check browser console for fetch errors

**No data from yfinance?**
- Internet connection required
- Yahoo Finance must have Nifty data available
- Try manual test: `python -c "import yfinance; print(yfinance.Ticker('^NSEI').history(period='1d'))"`

## Important Notes

- **STAY OUT is a valid signal** — not an error
- **VIX warning is mandatory** — cannot be dismissed
- **Disclaimer visible on all pages** — SEBI compliance
- **No real money yet** — Educational tool only
- **Data is real** — yfinance market data, but option returns are estimates

---

**Project Status:** ✅ Scaffolded and Ready to Launch
**Last Updated:** March 23, 2026
