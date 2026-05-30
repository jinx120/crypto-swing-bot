from __future__ import annotations

import pandas as pd
import pytest

from swingbot.signals.kronos_adapter import KronosAdapter


# ── helpers ────────────────────────────────────────────────────────────────

def _df(closes: list[float]) -> pd.DataFrame:
    """Minimal SwingBot candle DataFrame (same pattern as test_signals.py)."""
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": [c + 0.5 for c in closes],
        "low":  [c - 0.5 for c in closes],
        "close": closes,
        "volume": [100.0] * n,
    })


def _forecast_df(closes: list[float]) -> pd.DataFrame:
    """Minimal Kronos-format forecast DataFrame (datetime column, not ts)."""
    n = len(closes)
    return pd.DataFrame({
        "datetime": pd.date_range("2026-01-02", periods=n, freq="15min", tz="UTC"),
        "open":   closes,
        "high":   [c + 0.5 for c in closes],
        "low":    [c - 0.5 for c in closes],
        "close":  closes,
        "volume": [100.0] * n,
    })


class FakePredictor:
    """Satisfies PredictorProtocol without importing torch."""

    def __init__(self, forecast: pd.DataFrame, delay_s: float = 0.0):
        self._forecast = forecast
        self._delay_s = delay_s
        self.call_count = 0
        self.last_df_columns: list[str] = []

    def predict(self, df, x_timestamp, y_timestamp, pred_len,
                T, top_k, top_p, sample_count, verbose):
        import time
        self.last_df_columns = list(df.columns)
        self.call_count += 1
        if self._delay_s:
            time.sleep(self._delay_s)
        return self._forecast


# ── KronosAdapter tests ────────────────────────────────────────────────────

def test_candle_ts_renamed_to_datetime():
    """Adapter renames 'ts' → 'datetime' before calling predictor."""
    candles = _df([100.0, 101.0, 102.0])
    fcast = _forecast_df([103.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)
    adapter.forecast(candles)
    assert "datetime" in predictor.last_df_columns
    assert "ts" not in predictor.last_df_columns


def test_cache_calls_predictor_once():
    """Two forecast() calls with the same last candle ts hit cache; predictor called once."""
    candles = _df([100.0, 101.0, 102.0])
    fcast = _forecast_df([103.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)
    adapter.forecast(candles)
    adapter.forecast(candles)  # same candles → same last ts → cache hit
    assert predictor.call_count == 1


def test_cache_invalidated_on_new_ts():
    """A new last candle timestamp causes a fresh predictor call."""
    candles_a = _df([100.0, 101.0])
    candles_b = _df([100.0, 101.0, 102.0])  # one more bar → different last ts
    fcast = _forecast_df([103.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)
    adapter.forecast(candles_a)
    adapter.forecast(candles_b)
    assert predictor.call_count == 2


def test_forecast_returns_none_on_timeout():
    """Inference that exceeds timeout_s returns None without raising."""
    candles = _df([100.0, 101.0, 102.0])
    fcast = _forecast_df([103.0])
    slow = FakePredictor(fcast, delay_s=10.0)
    adapter = KronosAdapter(predictor=slow, pred_len=1, timeout_s=0.05)
    result = adapter.forecast(candles)
    assert result is None


def test_forecast_returns_none_on_predictor_exception():
    """An exception inside predict() returns None without raising."""
    class BrokenPredictor:
        def predict(self, **kwargs):
            raise RuntimeError("model exploded")

    candles = _df([100.0, 101.0, 102.0])
    adapter = KronosAdapter(predictor=BrokenPredictor(), pred_len=1)
    result = adapter.forecast(candles)
    assert result is None
