# Start with a basic function to fetch OHLCV data using ccxt:
import ccxt
import pandas as pd
# Load environment variables
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
load_dotenv()

# binance API keys from environment variables
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")

# initialize exchange
exchange = ccxt.binance()



# fetch OHLCV data -- testing the connection
def fetch_ohlcv(symbol="BTC/USDT", timeframe="15m", limit=100):
    exchange = ccxt.binance()
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["symbol"] = symbol
    df["timeframe"] = timeframe
    return df

# save to csv
def save_to_csv(df, symbol, timeframe):
    filename = f"data/raw/{symbol.replace('/', '')}_{timeframe}.csv"
    df.to_csv(filename, index=False)

# get OHLCV data
def get_ohlcv(symbol, timeframe, since, until):
    all_data = []
    since_ts = exchange.parse8601(since)
    until_ts = exchange.parse8601(until)

    while since_ts < until_ts:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since_ts, limit=1000)
        if not ohlcv:
            break
        all_data.extend(ohlcv)
        since_ts = ohlcv[-1][0] + 1  # move forward

    df = pd.DataFrame(all_data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df["symbol"] = symbol
    df["timeframe"] = timeframe
    return df

# save the raw data to csv
def save_raw_data(df, symbol, timeframe):
    path = f"data/raw/{symbol}_{timeframe}.csv"
    df.to_csv(path, index=False)

# Example usage:
df = get_ohlcv("BTC/USDT", "15m", "2023-01-01T00:00:00Z", "2023-01-02T00:00:00Z")
save_raw_data(df, "BTCUSDT", "15m")

