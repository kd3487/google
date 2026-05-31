import yfinance as yf
import pandas as pd

def fetch_real_nifty_data(period: str = "5d", interval: str = "15m") -> pd.DataFrame:
    """
    Fetches real historical price data for Nifty 50 (^NSEI) using yfinance.
    Returns a pandas DataFrame with normalized column names.
    """
    ticker = "^NSEI"
    try:
        nifty = yf.Ticker(ticker)
        df = nifty.history(period=period, interval=interval)

        if df.empty:
            print(f"Warning: Fetched data for {ticker} is empty.")
            return pd.DataFrame()

        # Normalize column names to lowercase for consistency
        df.columns = [col.lower() for col in df.columns]

        # yfinance returns index as DatetimeIndex, keep it or reset based on preference.
        # Keeping it as index is fine, or we can make it a column. We'll leave it as index.

        return df
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return pd.DataFrame()
