from __future__ import annotations

import pandas as pd
import pytest

from swingbot.backtest import _warmup_bars, precompute_forecasts, run_backtest
from swingbot.profile import StrategyProfile
from swingbot.signals.kronos_adapter import KronosAdapter
from swingbot.signals.kronos_forecast import KronosForecastSignal


def _df(n: int, close: float = 100.0) -> pd.DataFrame:
    closes = [close] * n
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": [c + 1.0 for c in closes],
        "low":  [c - 1.0 for c in closes],
        "close": closes,
        "volume": [500.0] * n,
    })


class RecordingPredictor:
    """Records every candle slice it receives so we can verify lookahead safety."""

    def __init__(self, forecast_close: float = 102.0, pred_len: int = 1):
        self._forecast_close = forecast_close
        self._pred_len = pred_len
        self.call_count = 0
        self.received_max_ts: list = []

    def predict(self, df, x_timestamp, y_timestamp, pred_len,
                T, top_p, sample_count):
        self.call_count += 1
        self.received_max_ts.append(df["datetime"].max())
        n = pred_len
        return pd.DataFrame({
            "datetime": pd.date_range(y_timestamp, periods=n, freq="15min", tz="UTC"),
            "open":   [self._forecast_close] * n,
            "high":   [self._forecast_close + 0.5] * n,
            "low":    [self._forecast_close - 0.5] * n,
            "close":  [self._forecast_close] * n,
            "volume": [100.0] * n,
        })


def _profile_with_kronos(adapter: KronosAdapter) -> StrategyProfile:
    return StrategyProfile(
        symbol="BTC/USD",
        regime_ma_period=10,
        atr_period=5,
        signals={
            "kronos_forecast": {
                "weight": 1.0,
                "pred_len": 1,
                "threshold_pct": 0.01,
                "min_history": 3,
                "_adapter": adapter,
            }
        },
        entry_threshold=0.5,
    )


def test_lookahead_safe():
    """At every backtest bar i, predictor receives candles[:i+1] only.

    Asserts the maximum timestamp in each predictor input equals
    df['ts'].iloc[i] — never a future bar.
    """
    df = _df(30)
    predictor = RecordingPredictor(forecast_close=102.0, pred_len=1)
    adapter = KronosAdapter(predictor=predictor, pred_len=1, timeout_s=5.0)
    profile = _profile_with_kronos(adapter)
    run_backtest(df, profile)

    warmup = _warmup_bars(profile)
    expected_ts = set(pd.Timestamp(df["ts"].iloc[i]) for i in range(warmup, len(df) - 1))
    for seen_ts in predictor.received_max_ts:
        assert seen_ts in expected_ts, (
            f"Predictor received ts {seen_ts} which is not a valid closed-bar boundary"
        )


def test_precompute_cache_avoids_duplicate_inference():
    """precompute_forecasts runs each bar exactly once."""
    df = _df(30)
    predictor = RecordingPredictor(forecast_close=102.0, pred_len=1)
    adapter = KronosAdapter(predictor=predictor, pred_len=1, timeout_s=5.0)
    profile = _profile_with_kronos(adapter)

    warmup = _warmup_bars(profile)
    cache = precompute_forecasts(df, adapter, warmup)

    assert len(cache) == len(df) - 1 - warmup
    assert predictor.call_count == len(df) - 1 - warmup


def test_precompute_skips_bars_before_warmup():
    """precompute_forecasts produces no entry for bars before warmup."""
    df = _df(30)
    predictor = RecordingPredictor(forecast_close=102.0, pred_len=1)
    adapter = KronosAdapter(predictor=predictor, pred_len=1, timeout_s=5.0)
    profile = _profile_with_kronos(adapter)

    warmup = _warmup_bars(profile)
    cache = precompute_forecasts(df, adapter, warmup)

    pre_warmup_ts = set(df["ts"].iloc[:warmup].tolist())
    for ts_key in cache:
        assert ts_key not in pre_warmup_ts


def test_run_backtest_with_kronos_signal_completes():
    """run_backtest doesn't crash when a KronosForecastSignal is present."""
    df = _df(30)
    predictor = RecordingPredictor(forecast_close=102.0, pred_len=1)
    adapter = KronosAdapter(predictor=predictor, pred_len=1, timeout_s=5.0)
    profile = _profile_with_kronos(adapter)
    trades, metrics = run_backtest(df, profile, starting_equity=10_000.0)
    assert isinstance(trades, list)
    assert metrics is not None
