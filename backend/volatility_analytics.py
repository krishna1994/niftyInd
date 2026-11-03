"""
Professional Volatility Analytics Module
Implements VRP, IV Rank, IV Percentile, and Portfolio Greeks
Based on industry-standard formulas used by professional traders
"""
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import yfinance as yf
import logging

logger = logging.getLogger(__name__)

class VolatilityAnalytics:
    """
    Professional-grade volatility analysis tools.
    Implements the quantitative patterns used by IBKR volatility traders.
    """
    
    @staticmethod
    def calculate_historical_volatility(prices: pd.Series, window: int = 30) -> float:
        """
        Calculate annualized historical volatility (Realized Volatility).
        Uses log returns, the industry standard.
        """
        log_returns = np.log(prices / prices.shift(1))
        return log_returns.rolling(window=window).std().iloc[-1] * np.sqrt(252) * 100
    
    @staticmethod
    def calculate_vrp(implied_vol: float, historical_vol: float) -> float:
        """
        Calculate Volatility Risk Premium (VRP).
        VRP = IV - RV
        
        Interpretation:
        - VRP > 5: Options are expensive, consider selling
        - VRP < -5: Options are cheap, consider buying
        - VRP near 0: Fair value
        """
        return implied_vol - historical_vol
    
    @staticmethod
    def calculate_iv_rank(current_iv: float, iv_history: pd.Series, lookback_days: int = 252) -> float:
        """
        Calculate IV Rank (0-100).
        Shows where current IV sits relative to the past year.
        
        Formula: (Current IV - Min IV) / (Max IV - Min IV) * 100
        """
        recent_iv = iv_history.tail(lookback_days)
        if len(recent_iv) < 10:
            return 50.0  # Not enough data
        
        min_iv = recent_iv.min()
        max_iv = recent_iv.max()
        
        if max_iv == min_iv:
            return 50.0
        
        iv_rank = ((current_iv - min_iv) / (max_iv - min_iv)) * 100
        return np.clip(iv_rank, 0, 100)
    
    @staticmethod
    def calculate_iv_percentile(current_iv: float, iv_history: pd.Series) -> float:
        """
        Calculate IV Percentile (0-100).
        Shows what percentage of historical IV values are below the current IV.
        
        More robust than IV Rank for long-term analysis.
        """
        if len(iv_history) < 10:
            return 50.0
        
        percentile = (iv_history < current_iv).sum() / len(iv_history) * 100
        return np.clip(percentile, 0, 100)
    
    @staticmethod
    def calculate_skew(call_iv: float, put_iv: float, spot: float, strike: float) -> Dict[str, Any]:
        """
        Calculate Put-Call Skew.
        
        Skew = Put IV - Call IV (for ATM strikes)
        
        Interpretation:
        - Positive skew: Puts are more expensive (fear premium)
        - Negative skew: Calls are more expensive (greed premium)
        - Normal market: Skew around +2 to +5
        """
        skew = put_iv - call_iv
        
        # Classify the skew regime
        if skew > 10:
            regime = "EXTREME_FEAR"
            signal = "Consider selling OTM puts (expensive)"
        elif skew > 5:
            regime = "HIGH_FEAR"
            signal = "Normal fear premium"
        elif skew < -5:
            regime = "GREED"
            signal = "Consider selling OTM calls (expensive)"
        else:
            regime = "NEUTRAL"
            signal = "Balanced market"
        
        return {
            "skew": round(skew, 2),
            "regime": regime,
            "signal": signal,
            "call_iv": round(call_iv, 2),
            "put_iv": round(put_iv, 2)
        }
    
    @staticmethod
    def calculate_portfolio_greeks(positions: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Calculate portfolio-level Greeks.
        
        Portfolio Delta: Net directional exposure (in shares of underlying)
        Portfolio Gamma: Rate of change of Delta
        Portfolio Vega: Sensitivity to 1% change in IV
        Portfolio Theta: Daily time decay
        
        This is the "Portfolio Risk Dashboard" used by professional traders.
        """
        total_delta = 0.0
        total_gamma = 0.0
        total_vega = 0.0
        total_theta = 0.0
        
        for pos in positions:
            quantity = pos.get("quantity", 0)
            delta = pos.get("delta", 0)
            gamma = pos.get("gamma", 0)
            vega = pos.get("vega", 0)
            theta = pos.get("theta", 0)
            
            # Aggregate Greeks (weighted by quantity)
            total_delta += delta * quantity * 100  # Convert to shares
            total_gamma += gamma * quantity * 100
            total_vega += vega * quantity * 100
            total_theta += theta * quantity * 100
        
        return {
            "portfolio_delta": round(total_delta, 2),
            "portfolio_gamma": round(total_gamma, 2),
            "portfolio_vega": round(total_vega, 2),
            "portfolio_theta": round(total_theta, 2),
            "delta_risk_level": "HIGH" if abs(total_delta) > 1000 else "MODERATE" if abs(total_delta) > 500 else "LOW",
            "gamma_risk_level": "HIGH" if abs(total_gamma) > 100 else "MODERATE" if abs(total_gamma) > 50 else "LOW"
        }
    
    @staticmethod
    def get_volatility_regime(iv_rank: float, vrp: float) -> Dict[str, str]:
        """
        Determine the current volatility regime and trading recommendation.
        
        This is the "master filter" used by professional volatility traders.
        """
        if iv_rank > 70 and vrp > 5:
            regime = "HIGH_IV_EXPENSIVE"
            recommendation = "SELL OPTIONS (Iron Condors, Credit Spreads)"
            confidence = "HIGH"
        elif iv_rank < 30 and vrp < -5:
            regime = "LOW_IV_CHEAP"
            recommendation = "BUY OPTIONS (Debit Spreads, Long Straddles)"
            confidence = "HIGH"
        elif iv_rank > 50 and vrp > 0:
            regime = "ELEVATED_IV"
            recommendation = "SELL OPTIONS (Moderate premium)"
            confidence = "MODERATE"
        elif iv_rank < 50 and vrp < 0:
            regime = "DEPRESSED_IV"
            recommendation = "BUY OPTIONS (Moderate discount)"
            confidence = "MODERATE"
        else:
            regime = "NEUTRAL"
            recommendation = "WAIT FOR BETTER SETUP"
            confidence = "LOW"
        
        return {
            "regime": regime,
            "recommendation": recommendation,
            "confidence": confidence,
            "iv_rank": round(iv_rank, 2),
            "vrp": round(vrp, 2)
        }


def _safe_float(val: float, default: float = 0.0) -> float:
    """Convert a float to a JSON-safe value (replaces NaN/Inf with default)."""
    import math
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def get_enhanced_volatility_analysis(symbol: str = "^NSEI") -> Dict[str, Any]:
    """
    Fetch and analyze volatility for a given symbol.
    Returns professional-grade volatility metrics with NaN-safe values.
    """
    try:
        # Fetch historical data
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1y")
        
        if hist.empty:
            return {"error": "No data available"}
        
        # Calculate Historical Volatility (30-day) — use log returns to avoid NaN
        log_returns = np.log(hist['Close'] / hist['Close'].shift(1)).dropna()
        if len(log_returns) < 30:
            return {"success": False, "error": "Insufficient data for volatility analysis"}
        
        hv_30 = float(log_returns.tail(30).std() * np.sqrt(252) * 100)
        hv_30 = _safe_float(hv_30, 15.0)
        
        # Estimate current IV
        current_iv = _safe_float(hv_30 * 1.2, 18.0)
        
        # Calculate rolling HV as IV proxy — use simple loop to avoid NaN
        hv_series = []
        prices = hist['Close'].values
        for i in range(30, len(prices)):
            chunk = np.log(prices[i-29:i+1] / prices[i-30:i]).std() * np.sqrt(252) * 100
            hv_series.append(_safe_float(chunk, hv_30))
        iv_history = pd.Series(hv_series)
        
        # Calculate IV Rank and IV Percentile
        iv_rank = _safe_float(VolatilityAnalytics.calculate_iv_rank(current_iv, iv_history), 50.0)
        iv_percentile = _safe_float(VolatilityAnalytics.calculate_iv_percentile(current_iv, iv_history), 50.0)
        
        # Calculate VRP
        vrp = _safe_float(VolatilityAnalytics.calculate_vrp(current_iv, hv_30), 0.0)
        
        # Get volatility regime
        regime = VolatilityAnalytics.get_volatility_regime(iv_rank, vrp)
        
        return {
            "success": True,
            "symbol": symbol,
            "current_iv": round(current_iv, 2),
            "historical_vol_30d": round(hv_30, 2),
            "vrp": round(vrp, 2),
            "iv_rank": round(iv_rank, 2),
            "iv_percentile": round(iv_percentile, 2),
            "volatility_regime": regime,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error in volatility analysis: {e}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Test the module
    result = get_enhanced_volatility_analysis("^NSEI")
    print(result)