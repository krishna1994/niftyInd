"""
Greeks Calculator
Implements the Black-Scholes model to calculate option Greeks (Delta, Gamma, Theta, Vega).
"""
import numpy as np
from scipy.stats import norm
from typing import Dict, Any

class GreeksCalculator:
    """
    Calculates option Greeks using the Black-Scholes model.
    Assumes European options.
    """
    
    @staticmethod
    def calculate_greeks(
        spot: float, 
        strike: float, 
        time_to_expiry: float, # In years
        risk_free_rate: float, # e.g., 0.07 for 7%
        volatility: float,     # Annualized volatility (e.g., 0.20 for 20%)
        option_type: str       # 'C' for Call, 'P' for Put
    ) -> Dict[str, float]:
        """
        Calculate Delta, Gamma, Theta, and Vega for a single option contract.
        """
        if time_to_expiry <= 0:
            return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}

        # Calculate d1 and d2
        d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * volatility**2) * time_to_expiry) / (volatility * np.sqrt(time_to_expiry))
        d2 = d1 - volatility * np.sqrt(time_to_expiry)

        # Standard Normal PDF and CDF
        phi = norm.pdf(d1)
        Phi = norm.cdf(d1)
        Phi_d2 = norm.cdf(d2)

        if option_type.upper() == 'C':
            # Call Delta
            delta = Phi
            # Call Theta
            theta = (- (spot * phi * volatility) / (2 * np.sqrt(time_to_expiry)) 
                     - risk_free_rate * strike * np.exp(-risk_free_rate * time_to_expiry) * Phi_d2) / 365
        else:
            # Put Delta
            delta = Phi - 1
            # Put Theta
            theta = (- (spot * phi * volatility) / (2 * np.sqrt(time_to_expiry)) 
                     + risk_free_rate * strike * np.exp(-risk_free_rate * time_to_expiry) * (1 - Phi_d2)) / 365

        # Gamma (same for Call and Put)
        gamma = phi / (spot * volatility * np.sqrt(time_to_expiry))
        
        # Vega (same for Call and Put)
        vega = (spot * phi * np.sqrt(time_to_expiry)) / 100 # Per 1% change in vol

        return {
            "delta": float(delta),
            "gamma": float(gamma),
            "theta": float(theta),
            "vega": float(vega)
        }

    @staticmethod
    def calculate_implied_volatility(
        market_price: float, 
        spot: float, 
        strike: float, 
        time_to_expiry: float, 
        risk_free_rate: float, 
        option_type: str
    ) -> float:
        """
        Estimates Implied Volatility using the Newton-Raphson method.
        """
        # Initial guess for volatility
        vol = 0.3 
        max_iter = 100
        precision = 1.0e-5

        for i in range(max_iter):
            greeks = GreeksCalculator.calculate_greeks(spot, strike, time_to_expiry, risk_free_rate, vol, option_type)
            
            # Calculate theoretical price
            d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * vol**2) * time_to_expiry) / (vol * np.sqrt(time_to_expiry))
            d2 = d1 - vol * np.sqrt(time_to_expiry)
            
            if option_type.upper() == 'C':
                price = spot * norm.cdf(d1) - strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
            else:
                price = strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)
            
            diff = market_price - price
            if abs(diff) < precision:
                return vol
            
            # Vega is the derivative of price with respect to volatility
            vega = greeks["vega"] * 100 # Convert back from 1% to absolute
            if vega == 0:
                break
                
            vol = vol + diff / vega
            
        return vol