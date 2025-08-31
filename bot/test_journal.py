from journal import append_trade

sample_record = {
    "ts_decision_utc": "2025-08-30T09:00:00Z",
    "symbol": "BTC/USDT",
    "timeframe": "15m",
    "bar_ts": "2025-08-30T08:45:00Z",
    "signal": "BUY",
    "prob_up": 0.62,
    "entry_rule": "RSI breakout",
    "price_ref": 27350.0,
    "position_before": 0.0,
    "order_side": "BUY",
    "order_qty": 0.001,
    "order_type": "MARKET",
    "order_id": "abc123",
    "order_status": "FILLED",
    "fill_price": 27352.0,
    "fees": 0.1,
    "position_after": 0.001,
    "sl": 27000.0,
    "tp": 27800.0,
    "reason": "Momentum spike",
    "features_snapshot": "{}",
    "model_version": "v1.0",
    "pnl_realized": 0.0,
    "pnl_unrealized": 0.0
}

append_trade(sample_record)