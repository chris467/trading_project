import pandas as pd
# Clean and preprocess OHLCV data
def clean_ohlcv(df, timeframe):
    df = df.set_index("timestamp").sort_index()
    freq_map = {
        "1m": "1min",
        "5m": "5min", 
        "15m": "15min", 
        "1h": "1H"
        }
    freq = freq_map.get(timeframe, "15min")

    df = df.resample(freq).ffill()
    df = df.reset_index()

    df["symbol"] = df["symbol"].iloc[0]
    df["timeframe"] = timeframe

    expected_cols = ["timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"]
    df = df[expected_cols]

    return df

# Add validation checks
def validate_ohlcv(df):
    assert df["timestamp"].is_monotonic_increasing, "Timestamps not increasing"
    assert df["timestamp"].dt.tz is None, "Timestamps must be naive UTC"

# save cleaned data
def save_clean_data(df, symbol, timeframe):
    path = f"data/processed/{symbol}_{timeframe}.parquet"
    df.to_parquet(path, index=False)

# test with raw file -- read it in, clean, validate, and save
raw = pd.read_csv("data/raw/BTCUSDT_15m.csv", parse_dates=["timestamp"])
clean = clean_ohlcv(raw, "15m")
validate_ohlcv(clean)
save_clean_data(clean, "BTCUSDT", "15m")