"""
Signal generation engine - determines BUY CE / BUY PE / STAY OUT based on indicators
"""
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Indicator weights for confidence calculation
# v3 — Reverted to proven CANDLE-only weights after empirical testing
#
# Backtest findings (1Y walk-forward):
#   RSI momentum: never fires (RSI stays 45-55 neutral when CANDLE signals occur)
#   ADX filter:   fires on 93% of trades, STRONG NEGATIVE (systematic bullish bias)
#   EMA:          positive but only fires on ~50% of CANDLE trades
#   CANDLE:       the ONLY reliable predictor — 62.5% win rate, +22.5% vs baseline
#
#   ACTIVE:
#     CANDLE:     62.5% win rate, +22.5% vs baseline → STRONG POSITIVE  (weight 1.5)
#     MACD:       40.0% win rate,  0.0% vs baseline → NEUTRAL, always fires (weight 1.0)
#     SUPERTREND: 40.0% win rate,  0.0% vs baseline → NEUTRAL, always fires (weight 1.0)
#
#   DISABLED (weight=0 but functions kept for display/future use):
#     RSI:        never fires in momentum mode with daily Nifty data     (weight 0.0)
#     EMA:        positive but insufficient data points to rely on       (weight 0.0)
#     ADX:        STRONG NEGATIVE — systematic bullish bias              (weight 0.0)
#     BOLLINGER:  never fires in practice                                (weight 0.0)
#     STOCH_RSI:  never fires in practice                                (weight 0.0)
#     VOLUME:     never fires in practice                                (weight 0.0)
#
# MAX_POSSIBLE_SCORE = 1.0 + 1.0 + 1.5 = 3.5
# At 60% threshold: need 2.1 points
#   MACD(full=1.0) + SUPERTREND(1.0) = 2.0 → 57.1% → NO signal (just below 60%)
#   MACD + SUPERTREND + CANDLE(1.5) = 3.5 → 100% → SIGNAL
# CANDLE is effectively required for any signal to be generated.
WEIGHTS = {
    "rsi": 0.0,        # DISABLED: never fires in momentum mode with daily data
    "macd": 1.0,       # ACTIVE: core trend indicator (always fires)
    "bollinger": 0.0,  # DISABLED: never fires in practice
    "ema": 0.0,        # DISABLED: insufficient data points to rely on
    "adx": 0.0,        # DISABLED: STRONG NEGATIVE — systematic bullish bias
    "supertrend": 1.0, # ACTIVE: core trend indicator (always fires)
    "stoch_rsi": 0.0,  # DISABLED: never fires in practice
    "volume": 0.0,     # DISABLED: never fires in practice
    "candle": 1.5,     # ACTIVE: best predictor — REQUIRED to reach 60% threshold
    "atr": 0.0,        # Unchanged: used for stop-loss sizing only
}

MAX_POSSIBLE_SCORE = sum(w for k, w in WEIGHTS.items() if k != "atr")

def score_rsi(rsi_value):
    """Score RSI as a MOMENTUM indicator (not reversal).
    In a trending market like Nifty, RSI extremes signal continuation, not reversal.
    RSI > 65 = strong bullish momentum, RSI < 35 = strong bearish momentum.
    """
    if pd.isna(rsi_value):
        return {"bull": 0.0, "bear": 0.0, "label": "RSI N/A", "score": 0.0}

    if rsi_value > 65:
        return {"bull": 0.9, "bear": 0.0, "label": f"Strong bullish momentum (RSI={rsi_value:.0f})", "score": 0.9}
    elif rsi_value > 55:
        return {"bull": 0.6, "bear": 0.0, "label": f"Bullish momentum (RSI={rsi_value:.0f})", "score": 0.6}
    elif rsi_value < 35:
        return {"bull": 0.0, "bear": 0.9, "label": f"Strong bearish momentum (RSI={rsi_value:.0f})", "score": 0.9}
    elif rsi_value < 45:
        return {"bull": 0.0, "bear": 0.6, "label": f"Bearish momentum (RSI={rsi_value:.0f})", "score": 0.6}
    else:
        return {"bull": 0.2, "bear": 0.2, "label": f"Neutral momentum (RSI={rsi_value:.0f})", "score": 0.2}

def score_macd(macd, signal, histogram):
    """Score MACD for bullish/bearish signal"""
    if pd.isna(macd) or pd.isna(signal):
        return {"bull": 0.0, "bear": 0.0, "label": "MACD N/A", "score": 0.0}
    
    # MACD above signal = bullish, below = bearish
    if macd > signal and histogram > 0:
        return {"bull": 1.0, "bear": 0.0, "label": "Bullish crossover + rising histogram", "score": 1.0}
    elif macd < signal and histogram < 0:
        return {"bull": 0.0, "bear": 1.0, "label": "Bearish crossover + falling histogram", "score": 1.0}
    elif macd > signal:
        return {"bull": 0.6, "bear": 0.1, "label": "MACD above signal (bullish)", "score": 0.6}
    else:
        return {"bull": 0.1, "bear": 0.6, "label": "MACD below signal (bearish)", "score": 0.6}

def score_bollinger(close, upper, mid, lower, pct_b):
    """Score Bollinger Bands"""
    if pd.isna(pct_b):
        return {"bull": 0.0, "bear": 0.0, "label": "Bollinger N/A", "score": 0.0}
    
    if pct_b < 0.2:
        return {"bull": 0.7, "bear": 0.1, "label": "Price near lower band — oversold", "score": 0.6}
    elif pct_b > 0.8:
        return {"bull": 0.1, "bear": 0.7, "label": "Price near upper band — overbought", "score": 0.6}
    else:
        return {"bull": 0.3, "bear": 0.3, "label": "Price in middle band — neutral", "score": 0.3}

def score_ema_stack(close, ema9, ema21, ema50, ema200):
    """Score EMA alignment"""
    if pd.isna(ema9) or pd.isna(ema200):
        return {"bull": 0.0, "bear": 0.0, "aligned": 0, "label": "EMA N/A", "score": 0.0}
    
    aligned_bull = 0
    aligned_bear = 0
    
    if ema9 > ema21 > ema50 > ema200:
        aligned_bull = 4
    elif ema9 > ema21 > ema50 and ema50 > ema200:
        aligned_bull = 3
    elif ema9 > ema21:
        aligned_bull = 2
    elif ema9 > ema200:
        aligned_bull = 1
    
    if ema9 < ema21 < ema50 < ema200:
        aligned_bear = 4
    elif ema9 < ema21 < ema50 and ema50 < ema200:
        aligned_bear = 3
    elif ema9 < ema21:
        aligned_bear = 2
    elif ema9 < ema200:
        aligned_bear = 1
    
    bull_score = aligned_bull * 0.25
    bear_score = aligned_bear * 0.25
    
    if aligned_bull == 4:
        label = "Full bullish EMA stack (4/4)"
    elif aligned_bear == 4:
        label = "Full bearish EMA stack (4/4)"
    elif aligned_bull > 0:
        label = f"Bullish EMA alignment ({aligned_bull}/4)"
    elif aligned_bear > 0:
        label = f"Bearish EMA alignment ({aligned_bear}/4)"
    else:
        label = "EMAs mixed"
    
    return {"bull": bull_score, "bear": bear_score, "aligned": max(aligned_bull, aligned_bear), "label": label, "score": max(bull_score, bear_score)}

def score_adx(adx_value, plus_di, minus_di):
    """Score ADX as a TREND STRENGTH amplifier (not directional indicator).
    ADX measures trend strength only — direction comes from +DI/-DI.
    ADX > 20: trend strong enough to sustain a move → amplify in DI direction.
    ADX < 20: choppy/ranging market → weak signal, penalize slightly.
    """
    if pd.isna(adx_value):
        return {"bull": 0.0, "bear": 0.0, "trend_strength": "WEAK", "label": "ADX N/A", "score": 0.0}

    trend_strength = "STRONG" if adx_value > 25 else ("MODERATE" if adx_value > 20 else "WEAK")

    if adx_value > 20:
        # Scale strength 0→1 based on ADX (20=0.67, 30=1.0, capped at 1.0)
        strength = min(1.0, adx_value / 30)
        if plus_di > minus_di:
            return {"bull": strength, "bear": 0.0, "trend_strength": trend_strength,
                    "label": f"Trend confirmed bullish (ADX={adx_value:.0f})", "score": strength}
        else:
            return {"bull": 0.0, "bear": strength, "trend_strength": trend_strength,
                    "label": f"Trend confirmed bearish (ADX={adx_value:.0f})", "score": strength}
    else:
        # Weak/ranging market — slight penalty to discourage options buying
        return {"bull": 0.1, "bear": 0.1, "trend_strength": "WEAK",
                "label": f"Weak trend (ADX={adx_value:.0f}) — avoid options buying", "score": 0.1}

def score_supertrend(close, supertrend, direction):
    """Score Supertrend"""
    if pd.isna(supertrend) or pd.isna(direction):
        return {"bull": 0.0, "bear": 0.0, "label": "Supertrend N/A", "score": 0.0}
    
    if direction < 0:  # Bullish
        return {"bull": 1.0, "bear": 0.0, "label": "Supertrend: price above line (bullish)", "score": 1.0}
    else:  # Bearish
        return {"bull": 0.0, "bear": 1.0, "label": "Supertrend: price below line (bearish)", "score": 1.0}

def score_stoch_rsi(stoch_k, stoch_d):
    """Score Stochastic RSI"""
    if pd.isna(stoch_k) or pd.isna(stoch_d):
        return {"bull": 0.0, "bear": 0.0, "label": "Stoch RSI N/A", "score": 0.0}
    
    if stoch_k < 20:
        return {"bull": 0.6, "bear": 0.1, "label": "Oversold (bullish reversal zone)", "score": 0.6}
    elif stoch_k > 80:
        return {"bull": 0.1, "bear": 0.6, "label": "Overbought (bearish reversal zone)", "score": 0.6}
    elif stoch_k > stoch_d:
        return {"bull": 0.4, "bear": 0.2, "label": "%K above %D (bullish momentum)", "score": 0.4}
    else:
        return {"bull": 0.2, "bear": 0.4, "label": "%K below %D (bearish momentum)", "score": 0.4}

def score_volume(volume_ratio):
    """Score volume ratio"""
    if pd.isna(volume_ratio):
        return {"bull": 0.0, "bear": 0.0, "label": "Volume N/A", "score": 0.0}
    
    if volume_ratio > 1.5:
        return {"bull": 0.3, "bear": 0.3, "label": f"High volume surge ({volume_ratio:.2f}x avg)", "score": 0.5}
    elif volume_ratio > 1.2:
        return {"bull": 0.25, "bear": 0.25, "label": f"Above average volume ({volume_ratio:.2f}x)", "score": 0.4}
    else:
        return {"bull": 0.1, "bear": 0.1, "label": "Low volume", "score": 0.2}

def score_candle_pattern(pattern):
    """Score candle pattern"""
    if pattern == "Bullish Engulfing":
        return {"bull": 1.0, "bear": 0.0, "label": "Bullish Engulfing detected", "score": 1.0}
    elif pattern == "Bearish Engulfing":
        return {"bull": 0.0, "bear": 1.0, "label": "Bearish Engulfing detected", "score": 1.0}
    else:
        return {"bull": 0.0, "bear": 0.0, "label": "No significant pattern", "score": 0.0}

def generate_signal(df, vix, confidence_threshold=60.0, pcr_data=None):
    """
    Generate BUY CE / BUY PE / STAY OUT signal based on indicator scores

    Logic:
    - Bull signal if bull_confidence >= threshold AND bull > bear * 1.2
    - Bear signal if bear_confidence >= threshold AND bear > bull * 1.2
    - STAY OUT otherwise
    - VIX adjustment: reduce confidence when VIX > 20
    - PCR adjustment: factor in Put-Call Ratio sentiment
    """
    logger.info("Generating signal...")
    
    latest = df.iloc[-1]
    
    # Score all indicators
    scores = {
        "rsi": score_rsi(latest['RSI']),
        "macd": score_macd(latest['MACD'], latest['MACD_Signal'], latest['MACD_Hist']),
        "bollinger": score_bollinger(latest['Close'], latest['BB_Upper'], latest['BB_Mid'], latest['BB_Lower'], latest['BB_PctB']),
        "ema": score_ema_stack(latest['Close'], latest['EMA9'], latest['EMA21'], latest['EMA50'], latest['EMA200']),
        "adx": score_adx(latest['ADX'], latest['Plus_DI'], latest['Minus_DI']),
        "supertrend": score_supertrend(latest['Close'], latest['Supertrend'], latest['Supertrend_Dir']),
        "stoch_rsi": score_stoch_rsi(latest['Stoch_K'], latest['Stoch_D']),
        "volume": score_volume(latest['Volume_Ratio']),
        "candle": score_candle_pattern(latest['Candle_Pattern']),
    }
    
    # Calculate weighted confidence
    bull_confidence = 0.0
    bear_confidence = 0.0
    agreed_indicators = []
    
    for indicator, score_data in scores.items():
        weight = WEIGHTS.get(indicator, 1.0)
        bull_confidence += score_data["bull"] * weight
        bear_confidence += score_data["bear"] * weight
        
        # Only include in agreed_indicators if the indicator has non-zero weight
        if score_data["score"] > 0.6 and weight > 0:
            if score_data["bull"] > score_data["bear"]:
                agreed_indicators.append(indicator.upper())
            elif score_data["bear"] > score_data["bull"]:
                agreed_indicators.append(indicator.upper())
    
    bull_confidence = (bull_confidence / MAX_POSSIBLE_SCORE) * 100
    bear_confidence = (bear_confidence / MAX_POSSIBLE_SCORE) * 100
    
    # VIX adjustment - reduce confidence when VIX is high
    vix_penalty = 0
    if vix > 28:
        vix_penalty = 20  # Block signals when VIX is extremely high
        logger.warning(f"VIX at {vix:.2f} - applying 20% confidence penalty")
    elif vix > 22:
        vix_penalty = 10  # Reduce confidence when VIX is elevated
        logger.info(f"VIX at {vix:.2f} - applying 10% confidence penalty")
    elif vix > 20:
        vix_penalty = 5  # Minor penalty for moderately high VIX
        logger.info(f"VIX at {vix:.2f} - applying 5% confidence penalty")
    
    bull_confidence = max(0, bull_confidence - vix_penalty)
    bear_confidence = max(0, bear_confidence - vix_penalty)
    
    # PCR adjustment - factor in Put-Call Ratio if available
    pcr_adjustment = 0
    pcr_signal = "NEUTRAL"
    if pcr_data:
        pcr = pcr_data.get("pcr", 1.0)
        pcr_signal = pcr_data.get("pcr_signal", "NEUTRAL")
        
        if pcr > 1.2:  # High PCR = bearish sentiment = contrarian bullish
            bull_confidence += 3
            logger.info(f"PCR at {pcr:.2f} (BULLISH) - adding 3% to bull confidence")
        elif pcr < 0.8:  # Low PCR = bullish sentiment = contrarian bearish
            bear_confidence += 3
            logger.info(f"PCR at {pcr:.2f} (BEARISH) - adding 3% to bear confidence")
    
    # Determine signal
    signal = "STAY OUT"
    direction = "NEUTRAL"
    
    if bull_confidence >= confidence_threshold and bull_confidence > bear_confidence * 1.2:
        signal = "BUY CE"
        direction = "BULLISH"
    elif bear_confidence >= confidence_threshold and bear_confidence > bull_confidence * 1.2:
        signal = "BUY PE"
        direction = "BEARISH"
    
    adx_trend = scores["adx"].get("trend_strength", "NEUTRAL")
    
    logger.info(f"Signal: {signal} | Bull: {bull_confidence:.1f}% | Bear: {bear_confidence:.1f}%")
    
    return {
        "signal": signal,
        "direction": direction,
        "confidence": max(bull_confidence, bear_confidence),
        "bull_confidence": bull_confidence,
        "bear_confidence": bear_confidence,
        "adx_trend_strength": adx_trend,
        "agreed_indicators": agreed_indicators,
        "indicators": {
            "rsi": {**scores["rsi"], "value": float(latest['RSI']) if not pd.isna(latest['RSI']) else 0},
            "macd": {**scores["macd"], "value": float(latest['MACD']) if not pd.isna(latest['MACD']) else 0, "signal_line": float(latest['MACD_Signal']) if not pd.isna(latest['MACD_Signal']) else 0, "histogram": float(latest['MACD_Hist']) if not pd.isna(latest['MACD_Hist']) else 0},
            "bollinger": {**scores["bollinger"], "upper": float(latest['BB_Upper']) if not pd.isna(latest['BB_Upper']) else 0, "mid": float(latest['BB_Mid']) if not pd.isna(latest['BB_Mid']) else 0, "lower": float(latest['BB_Lower']) if not pd.isna(latest['BB_Lower']) else 0, "pct_b": float(latest['BB_PctB']) if not pd.isna(latest['BB_PctB']) else 0},
            "ema": {**scores["ema"], "ema9": float(latest['EMA9']) if not pd.isna(latest['EMA9']) else 0, "ema21": float(latest['EMA21']) if not pd.isna(latest['EMA21']) else 0, "ema50": float(latest['EMA50']) if not pd.isna(latest['EMA50']) else 0, "ema200": float(latest['EMA200']) if not pd.isna(latest['EMA200']) else 0},
            "adx": {**scores["adx"], "value": float(latest['ADX']) if not pd.isna(latest['ADX']) else 0, "plus_di": float(latest['Plus_DI']) if not pd.isna(latest['Plus_DI']) else 0, "minus_di": float(latest['Minus_DI']) if not pd.isna(latest['Minus_DI']) else 0},
            "supertrend": {**scores["supertrend"], "value": float(latest['Supertrend']) if not pd.isna(latest['Supertrend']) else 0, "direction": "BULLISH" if latest['Supertrend_Dir'] < 0 else "BEARISH"},
            "stoch_rsi": {**scores["stoch_rsi"], "k": float(latest['Stoch_K']) if not pd.isna(latest['Stoch_K']) else 0, "d": float(latest['Stoch_D']) if not pd.isna(latest['Stoch_D']) else 0},
            "atr": {"value": float(latest['ATR']) if not pd.isna(latest['ATR']) else 0, "signal": "NEUTRAL", "label": "ATR used for stop-loss sizing"},
            "volume": {**scores["volume"], "ratio": float(latest['Volume_Ratio']) if not pd.isna(latest['Volume_Ratio']) else 0},
            "candle_pattern": {**scores["candle"], "pattern": latest['Candle_Pattern']},
        }
    }

def suggest_strikes(signal_result, latest_row):
    """Suggest strikes and levels based on signal"""
    spot = latest_row['Close']
    atr = latest_row['ATR']
    
    # ATM strike (nearest 100)
    atm = round(spot / 100) * 100
    
    if signal_result["signal"] == "BUY CE":
        recommended = atm + 100
        aggressive = atm + 200
        stop_loss_level = spot - 1.5 * atr
        target_1 = spot + 1.5 * atr
        target_2 = spot + 2.5 * atr
    elif signal_result["signal"] == "BUY PE":
        recommended = atm - 100
        aggressive = atm - 200
        stop_loss_level = spot + 1.5 * atr
        target_1 = spot - 1.5 * atr
        target_2 = spot - 2.5 * atr
    else:  # STAY OUT
        recommended = atm
        aggressive = atm
        stop_loss_level = spot
        target_1 = spot
        target_2 = spot
    
    return {
        "atm": f"{atm} {'PE' if signal_result['direction'] == 'BEARISH' else 'CE'}",
        "recommended": f"{int(recommended)} {'PE' if signal_result['direction'] == 'BEARISH' else 'CE'}",
        "aggressive": f"{int(aggressive)} {'PE' if signal_result['direction'] == 'BEARISH' else 'CE'}",
        "stop_loss_level": float(stop_loss_level),
        "target_1": float(target_1),
        "target_2": float(target_2),
    }
