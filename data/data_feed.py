import yfinance as yf
import pandas as pd
import urllib.request
import json
import datetime
from data.models import OptionsChain, StrikeData

def fetch_real_nifty_data(period: str = "5d", interval: str = "1m") -> pd.DataFrame:
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

def fetch_real_nifty_options_chain() -> OptionsChain:
    """
    Fetches real options chain data for Nifty from Groww's free API.
    Returns an OptionsChain object.
    """
    url = "https://groww.in/v1/api/option_chain_service/v1/option_chain/nifty"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        response = urllib.request.urlopen(req)
        data = json.loads(response.read().decode('utf-8'))

        now = datetime.datetime.now()
        strikes = {}

        if "optionChain" in data and "optionChains" in data["optionChain"]:
            expiry_str = data["optionChain"]["expiryDetailsDto"]["currentExpiry"]
            expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d").date()

            for item in data["optionChain"]["optionChains"]:
                strike_price = float(item["strikePrice"]) / 100.0 # Groww returns strike * 100

                call_data = item.get("callOption", {})
                put_data = item.get("putOption", {})

                # Groww doesn't provide IV directly in this endpoint, defaulting to 15.0 for structural logic
                strikes[strike_price] = StrikeData(
                    strike=strike_price,
                    call_oi=float(call_data.get("openInterest", 0)),
                    put_oi=float(put_data.get("openInterest", 0)),
                    call_volume=float(call_data.get("volume", 0)),
                    put_volume=float(put_data.get("volume", 0)),
                    implied_volatility=15.0
                )

            return OptionsChain(timestamp=now, expiry_date=expiry_date, strikes=strikes)
    except Exception as e:
        print(f"Error fetching options chain: {e}")

    # Return empty options chain on failure
    return OptionsChain(timestamp=datetime.datetime.now(), expiry_date=datetime.date.today(), strikes={})
