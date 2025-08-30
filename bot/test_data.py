from data import fetch_ohlcv, save_to_csv

df = fetch_ohlcv()
save_to_csv(df, "BTC/USDT", "15m")