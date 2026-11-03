# Multi-Broker Integration & Option Strategy Builder - Implementation Plan

## Executive Summary
This document outlines the plan to integrate Interactive Brokers (IBKR) Ireland, enhance Zerodha integration, improve eToro support, and add a Sensibull-like option strategy builder to the niftyInd platform.

## Current State Analysis

### Zerodha Integration (✅ Fully Implemented)
- **Status:** Production-ready with full trading capabilities
- **API:** Kite Connect (official Python SDK)
- **Features:**
  - OAuth-based authentication with daily token refresh
  - Auto-login via TOTP (optional)
  - Order placement (Market, Limit, SL, SL-M)
  - GTT (Good Till Triggered) orders for automated exits
  - Portfolio monitoring (positions, holdings, margins)
  - Historical data access
  - Instrument lookup with exact symbol matching
- **Limitations:** Daily token expiry (requires re-login ~6am IST)

### eToro Integration (⚠️ Manual Entry Only)
- **Status:** Analysis-only (no trading API available)
- **API:** None (confirmed no public retail API)
- **Features:**
  - Manual portfolio entry
  - Live P&L tracking via yfinance
  - Technical analysis on holdings
  - BUY_MORE/HOLD/TRIM/SELL suggestions
- **Limitations:** Cannot fetch positions or place trades automatically

### IBKR Integration (❌ Not Implemented)
- **Status:** To be implemented
- **API Options:**
  1. **TWS API via ib_insync** (Recommended)
     - Most powerful and flexible
     - Requires TWS/IB Gateway running locally
     - Full trading + real-time data
     - Excellent Python library support
  2. **Client Portal API** (Alternative)
     - REST-based
     - Requires Client Portal Gateway
     - More limited than TWS API

## Implementation Phases

### Phase 1: Unified Broker Architecture (Week 1)

#### 1.1 Create Base Broker Interface
**File:** `backend/broker_base.py`
```python
class BaseBroker(ABC):
    - get_connection_status()
    - get_profile()
    - get_margins()
    - get_positions()
    - get_holdings()
    - place_order()
    - cancel_order()
    - get_quote()
    - get_option_chain()  # New for strategy builder
```

#### 1.2 Refactor Zerodha Client
**File:** `backend/zerodha_client.py`
- Wrap existing functions in a `ZerodhaBroker(BaseBroker)` class
- Maintain backward compatibility with existing code
- Add option chain fetching method

#### 1.3 Create Broker Manager
**File:** `backend/broker_manager.py`
- Singleton pattern to manage multiple broker connections
- Route requests to appropriate broker
- Aggregate portfolio across all brokers

### Phase 2: IBKR Integration (Week 2-3)

#### 2.1 IBKR Client Implementation
**File:** `backend/ibkr_client.py`
**Dependencies:** `ib_insync` (pip install ib_insync)

**Key Features:**
- Connection management (TWS/IB Gateway on localhost:7497 or 4001)
- Authentication handling
- Order placement with IBKR's contract system
- Position/portfolio monitoring
- Option chain data retrieval
- Real-time quotes

**Configuration:**
```python
# backend/.env additions
IBKR_HOST=127.0.0.1
IBKR_PORT=7497  # TWS paper trading
IBKR_CLIENT_ID=1
IBKR_ACCOUNT=DU123456  # Your IBKR account number
```

#### 2.2 IBKR Setup Documentation
**File:** `docs/IBKR_SETUP.md`
- How to install TWS/IB Gateway
- API configuration in TWS
- Paper trading vs live account setup
- Firewall/network considerations

### Phase 3: Option Strategy Builder (Week 3-4)

#### 3.1 Strategy Engine Core
**File:** `backend/strategy_builder.py`

**Strategy Templates:**
1. **Vertical Spreads**
   - Bull Call Spread
   - Bear Put Spread
   - Bull Put Spread (credit)
   - Bear Call Spread (credit)

2. **Straddles & Strangles**
   - Long Straddle
   - Short Straddle
   - Long Strangle
   - Short Strangle

3. **Iron Condors & Butterflies**
   - Iron Condor (already partially implemented)
   - Iron Butterfly
   - Long Call Butterfly
   - Long Put Butterfly

4. **Calendar Spreads**
   - Call Calendar
   - Put Calendar

**Core Functions:**
```python
class OptionStrategy:
    def __init__(self, legs: List[OptionLeg])
    def calculate_payoff(self, spot_prices: np.array) -> np.array
    def calculate_greeks(self) -> Dict[str, float]
    def get_max_profit(self) -> float
    def get_max_loss(self) -> float
    def get_breakevens(self) -> List[float]
    def get_margin_required(self, broker: BaseBroker) -> float
    def execute(self, broker: BaseBroker) -> Dict[str, Any]
```

#### 3.2 Greeks Calculator
**File:** `backend/greeks_calculator.py`
**Dependencies:** `scipy`, `numpy`

- Black-Scholes model for European options
- Implied volatility solver
- Delta, Gamma, Theta, Vega, Rho calculations
- Portfolio-level Greeks aggregation

#### 3.3 Strategy Analyzer
**File:** `backend/strategy_analyzer.py`

**Features:**
- Probability of Profit (POP) estimation
- Risk/Reward ratio
- Expected value calculation
- Optimal strike selection based on:
  - Current IV percentile
  - Delta targets
  - Risk tolerance
  - Capital constraints

### Phase 4: Enhanced ML Model Pipeline (Week 4-5)

#### 4.1 Real-time Data Ingestion
**File:** `backend/data_pipeline.py`

**Enhancements:**
- Stream live F&O data during market hours
- Intraday model updates (every 30 minutes during CAS window)
- Cross-asset data refresh (Bank Nifty, USD/INR, Dow, VIX)

#### 4.2 Automated Model Retraining
**File:** `backend/model_trainer.py`

**Features:**
- Scheduled retraining (daily at 6 PM IST after market close)
- Walk-forward validation on new data
- Model performance monitoring
- Automatic rollback if new model underperforms
- A/B testing framework for model versions

#### 4.3 Feature Engineering Pipeline
**File:** `backend/feature_engineering.py`

**New Features:**
- Options flow indicators (PCR changes, OI buildup)
- Cross-broker sentiment (aggregate positions across Zerodha + IBKR)
- Intraday volatility patterns
- Order book imbalance (if available from broker)

### Phase 5: API Endpoints (Week 5)

#### 5.1 Broker Management Endpoints
```
GET  /api/brokers/status          # All broker connection statuses
POST /api/brokers/connect/{name}  # Connect to specific broker
POST /api/brokers/disconnect/{name}
GET  /api/brokers/portfolio       # Aggregated portfolio
```

#### 5.2 Strategy Builder Endpoints
```
GET  /api/strategies/templates    # List all strategy templates
POST /api/strategies/analyze      # Analyze a custom strategy
POST /api/strategies/execute      # Execute strategy on broker
GET  /api/strategies/positions    # Active strategy positions
POST /api/strategies/close        # Close a strategy position
```

#### 5.3 Option Chain Endpoints
```
GET  /api/options/chain/{symbol}  # Get option chain
GET  /api/options/greeks          # Calculate Greeks for contracts
POST /api/options/scanner          # Scan for opportunities
```

### Phase 6: Frontend Updates (Week 6)

#### 6.1 Multi-Broker Dashboard
**File:** `frontend/src/pages/Brokers.jsx`
- Connection status cards for each broker
- Unified portfolio view
- Per-broker position breakdown

#### 6.2 Strategy Builder UI
**File:** `frontend/src/pages/StrategyBuilder.jsx`
- Visual strategy constructor (drag-and-drop legs)
- Live payoff diagram (using Chart.js or Recharts)
- Greeks display
- Risk metrics
- One-click execution

#### 6.3 Enhanced Options Chain
**File:** `frontend/src/pages/OptionsChain.jsx`
- Multi-broker option chain comparison
- IV percentile visualization
- OI change heatmap
- Quick strategy creation from chain

## Technical Considerations

### Security
- Store broker credentials encrypted in database
- Use environment variables for API keys
- Implement rate limiting on broker API calls
- Add 2FA for strategy execution

### Error Handling
- Graceful degradation if one broker is down
- Retry logic with exponential backoff
- Clear error messages for users
- Comprehensive logging

### Performance
- Cache option chain data (15-second TTL)
- Parallel broker API calls where possible
- Lazy loading of historical data
- Database indexing for fast queries

### Testing
- Unit tests for each broker client
- Integration tests for strategy execution
- Mock broker responses for CI/CD
- Paper trading mode for all strategies

## Dependencies to Add

```bash
# Backend
pip install ib_insync          # IBKR integration
pip install scipy              # Greeks calculation
pip install py_vollib          # Implied volatility
pip install pandas_ta          # Additional indicators

# Frontend
npm install recharts           # Payoff diagrams
npm install react-dnd          # Drag-and-drop strategy builder
```

## Migration Path

1. **Week 1:** Deploy unified broker interface (no breaking changes)
2. **Week 2:** Add IBKR support (opt-in via .env)
3. **Week 3:** Release strategy builder (beta)
4. **Week 4:** Enhanced ML pipeline (background, no user impact)
5. **Week 5:** API endpoints (versioned, backward compatible)
6. **Week 6:** Frontend updates (progressive enhancement)

## Success Metrics

- [ ] All three brokers (Zerodha, IBKR, eToro) integrated
- [ ] 10+ option strategies available
- [ ] Strategy execution success rate > 95%
- [ ] ML model accuracy improvement > 5%
- [ ] User can manage portfolio across all brokers in one view
- [ ] Zero downtime during migration

## Risk Mitigation

1. **IBKR Connection Stability:** Implement heartbeat monitoring and auto-reconnect
2. **Order Execution Failures:** Add pre-flight checks (margin, contract validity)
3. **Data Quality:** Validate all external data before model training
4. **User Error:** Add confirmation dialogs for all real-money operations
5. **Regulatory Compliance:** Add disclaimers, ensure SEBI/SEC compliance

## Next Steps

1. Review and approve this plan
2. Set up development environment with IBKR paper trading account
3. Begin Phase 1 implementation
4. Weekly progress reviews