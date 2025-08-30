# Start with a basic function to fetch OHLCV data using ccxt:
import ccxt
import pandas as pd
# Load environment variables
from dotenv import load_dotenv
import os
load_dotenv()
api_key = os.getenv("BINANCE_API_KEY")
api_secret = os.getenv("BINANCE_API_SECRET")
# fetch OHLCV data
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