import numpy as np
import pandas as pd

from swingbot.indicators import rsi, atr, rolling_vwap, sma, lookback_return, ema


def _df(closes, highs=None, lows=None, vols=None):
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": highs if highs is not None else [c + 1 for c in closes],
        "low": lows if lows is not None else [c - 1 for c in closes],
        "close": closes,
        "volume": vols if vols is not None else [100.0] * n,
    })


def test_rsi_strong_uptrend_is_high():
    df = _df([float(i) for i in range(1, 40)])      # monotonic rise
    val = rsi(df["close"], period=14).iloc[-1]
    assert val > 95

def test_rsi_strong_downtrend_is_low():
    df = _df([float(i) for i in range(40, 1, -1)])   # monotonic fall
    val = rsi(df["close"], period=14).iloc[-1]
    assert val < 5

def test_atr_positive_and_finite():
    df = _df([10.0] * 30, highs=[11.0] * 30, lows=[9.0] * 30)
    val = atr(df, period=14).iloc[-1]
    assert val > 0 and np.isfinite(val)

def test_rolling_vwap_matches_manual():
    df = _df([10.0, 20.0], highs=[10.0, 20.0], lows=[10.0, 20.0], vols=[1.0, 3.0])
    # typical price == close here; vwap = (10*1 + 20*3)/(1+3) = 17.5
    assert abs(rolling_vwap(df, window=2).iloc[-1] - 17.5) < 1e-9

def test_sma_basic():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert sma(s, 2).iloc[-1] == 3.5


def test_ema_constant_series_equals_constant():
    s = pd.Series([5.0] * 50)
    result = ema(s, period=10)
    assert abs(result.iloc[-1] - 5.0) < 1e-9


def test_ema_warmup_is_nan_then_defined():
    s = pd.Series(range(1, 31), dtype="float64")
    result = ema(s, period=10)
    assert pd.isna(result.iloc[0])
    assert not pd.isna(result.iloc[-1])


def test_ema_more_responsive_than_sma_on_a_jump():
    s = pd.Series([10.0] * 20 + [20.0] * 5)
    e = ema(s, period=10).iloc[-1]
    m = sma(s, period=10).iloc[-1]
    assert e > m


def test_lookback_return():
    df = _df([100.0, 110.0])
    assert abs(lookback_return(df["close"], 1) - 0.10) < 1e-9
