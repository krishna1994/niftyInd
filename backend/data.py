"""
Data fetching module - retrieves Nifty and VIX data from yfinance
"""
import yfinance as yf
import pandas as pd
import logging

logger = logging.getLogger(__name__)

def fetch_nifty(period="6mo", interval="1d"):
    """
    Fetch Nifty 50 OHLCV data from yfinance.
    
    Args:
        period: "6mo", "1y", "2y", "3mo"
        interval: "1d", "1h", "15m"
    
    Returns:
        pandas DataFrame with OHLCV data
    """
    try:
        logger.info(f"Fetching Nifty data: period={period}, interval={interval}")
        
        nifty = yf.download(
            "^NSEI",  # Nifty 50 index ticker
            period=period,
            interval=interval,
            progress=False
        )
        
        if nifty.empty:
            raise ValueError("No data fetched for Nifty 50")

        # Handle MultiIndex columns from newer yfinance versions
        if isinstance(nifty.columns, pd.MultiIndex):
            nifty.columns = nifty.columns.get_level_values(0)

        # Normalize column names (strip whitespace)
        nifty.columns = [str(c).strip() for c in nifty.columns]

        # Drop 'Adj Close' if present, keep only OHLCV
        if 'Adj Close' in nifty.columns:
            nifty = nifty[['Open', 'High', 'Low', 'Close', 'Volume']]
        else:
            # Select only the 5 standard OHLCV columns
            ohlcv_cols = [c for c in ['Open', 'High', 'Low', 'Close', 'Volume'] if c in nifty.columns]
            nifty = nifty[ohlcv_cols]

        nifty.index.name = 'Date'
        
        logger.info(f"Fetched {len(nifty)} candles")
        return nifty
        
    except Exception as e:
        logger.error(f"Error fetching Nifty data: {str(e)}")
        raise

def fetch_vix():
    """
    Fetch current India VIX value from yfinance.
    
    Returns:
        float: Current VIX value
    """
    try:
        logger.info("Fetching India VIX data")
        
        vix_data = yf.download(
            "^INDIAVIX",  # India VIX ticker
            period="1d",
            interval="1d",
            progress=False
        )
        
        if vix_data.empty:
            logger.warning("No VIX data, returning default 15.0")
            return 15.0

        # Handle MultiIndex columns from newer yfinance versions
        if isinstance(vix_data.columns, pd.MultiIndex):
            vix_data.columns = vix_data.columns.get_level_values(0)

        vix_value = float(vix_data['Close'].iloc[-1])
        logger.info(f"Current VIX: {vix_value:.2f}")
        return vix_value
        
    except Exception as e:
        logger.error(f"Error fetching VIX data: {str(e)}")
        return 15.0  # Default fallback value

def fetch_vix_history(period="1y"):
    """
    Fetch historical India VIX data for backtesting.
    
    Args:
        period: "6mo", "1y", "2y"
    
    Returns:
        pandas Series with VIX values indexed by date
    """
    try:
        vix_history = yf.download(
            "^INDIAVIX",
            period=period,
            interval="1d",
            progress=False
        )
        
        if vix_history.empty:
            logger.warning("No VIX history, returning series of 15.0")
            return pd.Series(15.0, index=pd.date_range(periods=252))

        # Handle MultiIndex columns from newer yfinance versions
        if isinstance(vix_history.columns, pd.MultiIndex):
            vix_history.columns = vix_history.columns.get_level_values(0)

        return vix_history['Close']
        
    except Exception as e:
        logger.error(f"Error fetching VIX history: {str(e)}")
        return pd.Series(15.0, index=pd.date_range(periods=252))
