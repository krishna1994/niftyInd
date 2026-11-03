"""
Option Strategy Builder
Engine for creating, analyzing, and executing multi-leg option strategies.
"""
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from greeks_calculator import GreeksCalculator

@dataclass
class OptionLeg:
    strike: float
    option_type: str  # 'C' for Call, 'P' for Put
    quantity: int     # Positive for Long, Negative for Short
    entry_price: float
    expiry_days: int
    symbol: Optional[str] = None

class OptionStrategy:
    def __init__(self, name: str, legs: List[OptionLeg]):
        self.name = name
        self.legs = legs

    def calculate_payoff(self, spot_prices: np.array) -> np.array:
        """
        Calculate the total P&L of the strategy for a range of spot prices at expiry.
        """
        total_payoff = np.zeros_like(spot_prices)
        
        for leg in self.legs:
            if leg.option_type.upper() == 'C':
                # Call Payoff: Max(0, Spot - Strike) * Qty - (Entry * Qty)
                payoff = np.maximum(0, spot_prices - leg.strike) * leg.quantity
                cost = leg.entry_price * leg.quantity
            else:
                # Put Payoff: Max(0, Strike - Spot) * Qty - (Entry * Qty)
                payoff = np.maximum(0, leg.strike - spot_prices) * leg.quantity
                cost = leg.entry_price * leg.quantity
            
            # Note: If quantity is negative (Short), the cost is a credit (positive)
            # and the payoff is inverted.
            total_payoff += (payoff - cost)
            
        return total_payoff

    def get_metrics(self, current_spot: float, risk_free_rate: float = 0.07, volatility: float = 0.20) -> Dict[str, Any]:
        """
        Calculate Max Profit, Max Loss, Breakevens, and Aggregated Greeks.
        """
        # Generate a range of spot prices for analysis (+/- 20%)
        spot_range = np.linspace(current_spot * 0.8, current_spot * 1.2, 1000)
        payoffs = self.calculate_payoff(spot_range)
        
        max_profit = np.max(payoffs)
        max_loss = np.min(payoffs)
        
        # Find breakevens (where payoff crosses 0)
        breakevens = []
        for i in range(len(payoffs) - 1):
            if (payoffs[i] <= 0 and payoffs[i+1] >= 0) or (payoffs[i] >= 0 and payoffs[i+1] <= 0):
                # Linear interpolation for more precise breakeven
                frac = abs(payoffs[i]) / (abs(payoffs[i]) + abs(payoffs[i+1]))
                be = spot_range[i] + frac * (spot_range[i+1] - spot_range[i])
                breakevens.append(float(be))

        # Aggregate Greeks
        total_greeks = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
        t_years = 0 # Default, will be updated per leg
        
        for leg in self.legs:
            t_years = leg.expiry_days / 365.0
            g = GreeksCalculator.calculate_greeks(
                current_spot, leg.strike, t_years, risk_free_rate, volatility, leg.option_type
            )
            # Multiply by quantity (Short positions have negative Greeks)
            for k in total_greeks:
                total_greeks[k] += g[k] * leg.quantity

        return {
            "strategy_name": self.name,
            "max_profit": float(max_profit),
            "max_loss": float(max_loss),
            "breakevens": breakevens,
            "greeks": total_greeks,
            "payoff_data": {
                "spots": spot_range.tolist(),
                "payoffs": payoffs.tolist()
            }
        }

class StrategyTemplates:
    """Factory for common option strategies."""
    
    @staticmethod
    def bull_call_spread(spot: float, expiry: int, low_strike: float, high_strike: float, low_price: float, high_price: float):
        legs = [
            OptionLeg(low_strike, 'C', 1, low_price, expiry),
            OptionLeg(high_strike, 'C', -1, high_price, expiry)
        ]
        return OptionStrategy("Bull Call Spread", legs)

    @staticmethod
    def bear_put_spread(spot: float, expiry: int, high_strike: float, low_strike: float, high_price: float, low_price: float):
        legs = [
            OptionLeg(high_strike, 'P', 1, high_price, expiry),
            OptionLeg(low_strike, 'P', -1, low_price, expiry)
        ]
        return OptionStrategy("Bear Put Spread", legs)

    @staticmethod
    def iron_condor(spot: float, expiry: int, 
                    put_low: float, put_high: float, 
                    call_low: float, call_high: float,
                    p_low_p: float, p_high_p: float, 
                    c_low_p: float, c_high_p: float):
        legs = [
            OptionLeg(put_low, 'P', 1, p_low_p, expiry),
            OptionLeg(put_high, 'P', -1, p_high_p, expiry),
            OptionLeg(call_low, 'C', -1, c_low_p, expiry),
            OptionLeg(call_high, 'C', 1, c_high_p, expiry),
        ]
        return OptionStrategy("Iron Condor", legs)

    @staticmethod
    def straddle(spot: float, expiry: int, strike: float, call_price: float, put_price: float):
        legs = [
            OptionLeg(strike, 'C', 1, call_price, expiry),
            OptionLeg(strike, 'P', 1, put_price, expiry),
        ]
        return OptionStrategy("Long Straddle", legs)