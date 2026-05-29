import os
import pandas as pd
import pytest

from swingbot.data.alpaca import parse_timeframe, bars_to_df

CREDS = bool(os.getenv("ALPACA_API_KEY_ID") and os.getenv("ALPACA_API_SECRET_KEY"))


def test_parse_timeframe_minutes_hours():
    from alpaca.data.timeframe import TimeFrameUnit
    tf = parse_timeframe("15m")
    assert tf.amount_value == 15 and tf.unit_value == TimeFrameUnit.Minute
    tf2 = parse_timeframe("4h")
    assert tf2.amount_value == 4 and tf2.unit_value == TimeFrameUnit.Hour
    tf3 = parse_timeframe("1d")
    assert tf3.amount_value == 1 and tf3.unit_value == TimeFrameUnit.Day

def test_parse_timeframe_rejects_bad():
    with pytest.raises(ValueError):
        parse_timeframe("15x")

def test_bars_to_df_normalizes():
    rows = [
        {"timestamp": pd.Timestamp("2026-01-01T00:00:00Z"), "open": 1, "high": 2,
         "low": 0.5, "close": 1.5, "volume": 10},
        {"timestamp": pd.Timestamp("2026-01-01T00:15:00Z"), "open": 1.5, "high": 2.2,
         "low": 1.4, "close": 2.0, "volume": 12},
    ]
    df = bars_to_df(rows)
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert df["ts"].is_monotonic_increasing
    assert str(df["ts"].dt.tz) == "UTC"
    assert df["close"].dtype == float

@pytest.mark.skipif(not CREDS, reason="Alpaca creds not set")
def test_live_get_candles_smoke():
    from swingbot.data.alpaca import AlpacaData
    d = AlpacaData(os.environ["ALPACA_API_KEY_ID"], os.environ["ALPACA_API_SECRET_KEY"])
    df = d.get_candles("BTC/USD", "15m", lookback=50)
    assert len(df) > 0
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]

def test_fetch_window_days_scales_with_lookback():
    from swingbot.data.alpaca import fetch_window_days
    assert fetch_window_days("15m", 50) >= 1
    # 4h x 205 bars needs ~100 days; must be well over 30
    assert fetch_window_days("4h", 205) > 90
    # 1d x 205 bars needs ~600+ days
    assert fetch_window_days("1d", 205) > 500
    with __import__("pytest").raises(ValueError):
        fetch_window_days("15x", 10)
