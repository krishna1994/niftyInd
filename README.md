# Nifty Weekly Option Signal Analyzer

A professional-grade trading tool for analyzing Nifty 50 weekly options, generating directional signals, and managing multi-broker portfolios.

## 🚀 Features

- **Directional Signal Engine**: Computes technical indicators (RSI, MACD, EMA, ADX, Supertrend) to generate high-confidence BUY/SELL/STAY OUT signals.
- **CAS (Closing Auction Session) Analysis**: ML-powered analysis of the closing window to detect big-move risks and directional bias.
- **Multi-Broker Integration**: Unified portfolio view aggregating positions from Zerodha, IBKR, and eToro.
- **Iron Condor Strategy**: Automated strike suggestions and margin checks for range-bound premium selling.
- **Paper Trading (Dry Run)**: Risk-free environment to test signals with automated P&L tracking.
- **Auto-Trader**: Safety-first automated execution engine with GTT (Good Till Triggered) exit management.
- **Volatility Analytics**: Professional VRP, IV Rank, and IV Percentile analysis.

## 🛠️ Architecture

The application follows a decoupled client-server architecture:

### Backend (FastAPI)
- **Data Layer**: Fetches real-time and historical data via `yfinance` and NSE APIs.
- **Signal Engine**: Implements quantitative trading logic and technical analysis.
- **ML Layer**: Uses Random Forest models for CAS signal prediction.
- **Broker Manager**: An abstraction layer to handle different broker APIs (Zerodha, IBKR).
- **Database**: SQLite for caching backtests, logging signals, and storing paper trades.

### Frontend (React + Tailwind CSS)
- **State Management**: React hooks for real-time polling of signals and positions.
- **Visualization**: Framer Motion for smooth transitions and custom gauges for risk/confidence.
- **Responsive Design**: Optimized for both desktop and mobile monitoring.

## 📈 Code Flow

1. **Data Ingestion**: `data.py` $\rightarrow$ `indicators.py` $\rightarrow$ `signal_engine.py`.
2. **Signal Generation**: The backend computes indicators $\rightarrow$ applies regime filters (VIX) $\rightarrow$ generates a signal $\rightarrow$ suggests strikes.
3. **CAS Pipeline**: `cas_service.py` trains models on historical datasets $\rightarrow$ fetches live market snapshots $\rightarrow$ outputs a calibrated POP and bias.
4. **Execution**: `broker_manager.py` $\rightarrow$ `zerodha_client.py` / `ibkr_client.py` $\rightarrow$ Broker API.

## 📦 Installation & Setup

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local dev)
- Node.js 18+ (for local dev)

### Quick Start (Docker)
1. Clone the repository.
2. Create a `.env` file in `backend/` based on `.env.example`.
3. Run the application:
   ```bash
   docker-compose up --build
   ```
4. Access the dashboard at `http://localhost`.

### Local Development
**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## 🛡️ Safety & Risk Warning
This software is for informational and educational purposes. Trading options involves significant risk. The Auto-Trader is disabled by default and requires explicit manual activation. Always verify signals independently.