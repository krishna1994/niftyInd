"""
Pydantic response models for API endpoints (optional - for type safety)
"""
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class IndicatorData(BaseModel):
    value: Optional[float] = None
    signal: str
    label: str
    score: float

class StrikeData(BaseModel):
    atm: str
    recommended: str
    aggressive: str
    stop_loss_level: float
    target_1: float
    target_2: float

class SignalResponse(BaseModel):
    timestamp: str
    spot: float
    vix: float
    signal: str
    direction: str
    confidence: float
    bull_confidence: float
    bear_confidence: float
    adx_trend_strength: str
    vix_warning: bool
    vix_warning_message: Optional[str]
    strikes: StrikeData
    indicators: Dict[str, Any]
    ohlcv: List[Dict[str, Any]]

class BacktestSummary(BaseModel):
    total_signals: int
    buy_ce_signals: int
    buy_pe_signals: int
    stay_out_signals: int
    win_rate: float
    avg_return_per_trade: float
    best_trade: float
    worst_trade: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    avg_holding_days: float

class Trade(BaseModel):
    date: str
    signal: str
    confidence: float
    entry_spot: float
    strike: str
    exit_spot: float
    result: str
    pct_return: float
    holding_days: int
    indicators_agreed: List[str]

class BacktestResponse(BaseModel):
    summary: BacktestSummary
    trades: List[Trade]
    equity_curve: List[Dict[str, Any]]
    monthly_returns: List[Dict[str, Any]]
    win_by_indicator_combo: List[Dict[str, Any]]
