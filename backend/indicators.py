"""
Technical indicators calculation module
Computes RSI, MACD, Bollinger Bands, EMA, ADX, Supertrend, Stoch RSI, ATR, Volume, Candle Patterns
"""
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)

def compute_rsi(series, period=14):
    """Relative Strength Index (14-period)"""
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta.clip(upper=0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def compute_macd(series, fast=12, slow=26, signal_period=9):
    """MACD (12, 26, 9)"""
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal_period, adjust=False).mean()
    histogram = macd - signal_line
    return macd, signal_line, histogram

def compute_bollinger_bands(series, period=20, std_dev=2):
    """Bollinger Bands (20-period, 2 std dev)"""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    pct_b = (series - lower) / (upper - lower)
    return upper, sma, lower, pct_b

def compute_ema_stack(series):
    """EMA Stack: 9, 21, 50, 200 periods"""
    ema9 = series.ewm(span=9, adjust=False).mean()
    ema21 = series.ewm(span=21, adjust=False).mean()
    ema50 = series.ewm(span=50, adjust=False).mean()
    ema200 = series.ewm(span=200, adjust=False).mean()
    return ema9, ema21, ema50, ema200

def compute_adx(df, period=14):
    """Average Directional Index (14-period) with +DI and -DI"""
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    # True Range
    hl = high - low
    hc = (high - close.shift()).abs()
    lc = (low - close.shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    
    # Directional Movement
    up = high.diff()
    down = -low.diff()
    
    pos_dm = pd.Series(np.where((up > down) & (up > 0), up, 0), index=df.index)
    neg_dm = pd.Series(np.where((down > up) & (down > 0), down, 0), index=df.index)
    
    # Smooth DM and TR (14-period sum, then average)
    pos_di = 100 * (pos_dm.rolling(window=period).sum() / tr.rolling(window=period).sum())
    neg_di = 100 * (neg_dm.rolling(window=period).sum() / tr.rolling(window=period).sum())
    
    # DX and ADX
    dx = 100 * (abs(pos_di - neg_di) / (pos_di + neg_di + 1e-10))
    adx = dx.rolling(window=period).mean()
    
    return adx, pos_di, neg_di

def compute_atr(df, period=14):
    """Average True Range (14-period)"""
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    hl = high - low
    hc = (high - close.shift()).abs()
    lc = (low - close.shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    
    atr = tr.rolling(window=period).mean()
    return atr

def compute_supertrend(df, atr_period=10, multiplier=3.0):
    """Supertrend indicator based on ATR"""
    hl_avg = (df['High'] + df['Low']) / 2
    atr = compute_atr(df, atr_period)
    
    basic_ub = hl_avg + multiplier * atr
    basic_lb = hl_avg - multiplier * atr
    
    # Final upper and lower bands (avoid whipsaws)
    ub = basic_ub.copy()
    lb = basic_lb.copy()
    
    for i in range(1, len(df)):
        ub.iloc[i] = min(basic_ub.iloc[i], ub.iloc[i-1]) if df['Close'].iloc[i-1] > ub.iloc[i-1] else basic_ub.iloc[i]
        lb.iloc[i] = max(basic_lb.iloc[i], lb.iloc[i-1]) if df['Close'].iloc[i-1] < lb.iloc[i-1] else basic_lb.iloc[i]
    
    # Supertrend direction: -1 (bullish), 1 (bearish)
    direction = pd.Series(0, index=df.index)
    supertrend = pd.Series(0.0, index=df.index)
    
    for i in range(1, len(df)):
        if i == 0:
            direction.iloc[i] = 1
            supertrend.iloc[i] = ub.iloc[i]
        else:
            if direction.iloc[i-1] == 1:
                if df['Close'].iloc[i] <= lb.iloc[i]:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = ub.iloc[i]
                else:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = lb.iloc[i]
            else:
                if df['Close'].iloc[i] >= ub.iloc[i]:
                    direction.iloc[i] = 1
                    supertrend.iloc[i] = lb.iloc[i]
                else:
                    direction.iloc[i] = -1
                    supertrend.iloc[i] = ub.iloc[i]
    
    return supertrend, direction

def compute_stochastic_rsi(rsi, period=14, smooth_k=3, smooth_d=3):
    """Stochastic RSI (%K, %D)"""
    min_rsi = rsi.rolling(window=period).min()
    max_rsi = rsi.rolling(window=period).max()
    
    stoch_k = 100 * (rsi - min_rsi) / (max_rsi - min_rsi + 1e-10)
    stoch_d = stoch_k.rolling(window=smooth_d).mean()
    
    return stoch_k, stoch_d

def compute_volume_ratio(df, period=14):
    """Volume ratio (current volume vs average)"""
    avg_volume = df['Volume'].rolling(window=period).mean()
    volume_ratio = df['Volume'] / (avg_volume + 1e-10)
    return volume_ratio

def detect_candle_patterns(df):
    """Detect bullish/bearish candle patterns"""
    # Simplified pattern detection
    open_ = df['Open']
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    patterns = pd.Series("NONE", index=df.index)
    
    # Bearish Engulfing
    for i in range(1, len(df)):
        prev_body = (close.iloc[i-1] - open_.iloc[i-1])
        curr_body = (close.iloc[i] - open_.iloc[i])
        
        if prev_body > 0 and curr_body < 0:  # Prev bullish, curr bearish
            if abs(curr_body) > abs(prev_body) and close.iloc[i] < open_.iloc[i-1] and open_.iloc[i] > close.iloc[i-1]:
                patterns.iloc[i] = "Bearish Engulfing"
    
    # Bullish Engulfing
    for i in range(1, len(df)):
        prev_body = (close.iloc[i-1] - open_.iloc[i-1])
        curr_body = (close.iloc[i] - open_.iloc[i])
        
        if prev_body < 0 and curr_body > 0:  # Prev bearish, curr bullish
            if abs(curr_body) > abs(prev_body) and close.iloc[i] > open_.iloc[i-1] and open_.iloc[i] < close.iloc[i-1]:
                patterns.iloc[i] = "Bullish Engulfing"
    
    return patterns

def compute_all_indicators(df):
    """
    Compute all indicators at once.
    Includes the Volatility Squeeze (BB inside KC).
    """
    logger.info("Computing all indicators...")
    
    # Price-based indicators
    df['RSI'] = compute_rsi(df['Close'], 14)
    df['MACD'], df['MACD_Signal'], df['MACD_Hist'] = compute_macd(df['Close'])
    df['BB_Upper'], df['BB_Mid'], df['BB_Lower'], df['BB_PctB'] = compute_bollinger_bands(df['Close'])
    df['EMA9'], df['EMA21'], df['EMA50'], df['EMA200'] = compute_ema_stack(df['Close'])
    df['ADX'], df['Plus_DI'], df['Minus_DI'] = compute_adx(df)
    df['ATR'] = compute_atr(df)
    df['Supertrend'], df['Supertrend_Dir'] = compute_supertrend(df)
    df['Stoch_K'], df['Stoch_D'] = compute_stochastic_rsi(df['RSI'])
    df['Volume_Ratio'] = compute_volume_ratio(df)
    df['Candle_Pattern'] = detect_candle_patterns(df)

    # --- Volatility Squeeze Logic ---
    # 1. Bollinger Bands (20, 2) - already computed as BB_Upper/Lower
    # 2. Keltner Channels (20, 1.5)
    ma20 = df['Close'].rolling(window=20).mean()
    atr20 = compute_atr(df, period=20)
    df['KC_Upper'] = ma20 + (1.5 * atr20)
    df['KC_Lower'] = ma20 - (1.5 * atr20)

    # 3. Squeeze: BB is inside KC
    df['in_squeeze'] = (df['BB_Upper'] < df['KC_Upper']) & (df['BB_Lower'] > df['KC_Lower'])
    
    logger.info("All indicators computed successfully")
    return df
