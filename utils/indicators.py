import pandas as pd
import numpy as np

def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    """Calculate Simple Moving Average."""
    return series.rolling(window=period).mean()

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range (ATR)."""
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)

    return true_range.rolling(window=period).mean()

def is_volume_expanding(current_volume: float, volume_series: pd.Series, period: int = 20) -> bool:
    """Check if volume is expanding (current volume > 1.5 * SMA of volume)."""
    if len(volume_series) < period:
         return False
    sma_vol = calculate_sma(volume_series, period).iloc[-1]
    return current_volume > 1.5 * sma_vol

def calculate_bollinger_bands(series: pd.Series, period: int = 20, std_dev: int = 2):
    """Calculate Bollinger Bands and Bandwidth."""
    sma = calculate_sma(series, period)
    std = series.rolling(window=period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    bandwidth = (upper_band - lower_band) / sma
    return upper_band, lower_band, bandwidth

def detect_squeeze(df: pd.DataFrame, period: int = 20) -> bool:
    """
    Detect squeeze condition based on low Bollinger Bandwidth and ATR.
    Simple implementation: Bandwidth is in lowest 20th percentile of lookback window.
    """
    if len(df) < period * 2:
        return False

    _, _, bandwidth = calculate_bollinger_bands(df['close'], period)
    current_bw = bandwidth.iloc[-1]

    # Check if current bandwidth is very tight compared to recent history (squeeze)
    recent_bw = bandwidth.iloc[-period*2:]
    threshold = recent_bw.quantile(0.2)

    return current_bw <= threshold

def check_vwap_hold(price: float, vwap: float, threshold_pct: float = 0.002) -> bool:
    """Check if price is holding VWAP within a certain percentage (default 0.2%)."""
    if vwap == 0:
        return False
    return abs(price - vwap) / vwap <= threshold_pct
