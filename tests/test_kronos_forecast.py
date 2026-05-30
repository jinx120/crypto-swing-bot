from __future__ import annotations

import pandas as pd
import pytest

from swingbot.signals.kronos_adapter import KronosAdapter
from swingbot.signals.kronos_forecast import KronosForecastSignal
from swingbot.types import MarketContext


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


# ── KronosForecastSignal tests ────────────────────────────────────────────

def _make_signal(
    forecast_closes,
    min_history=3,
    threshold_pct=0.02,
    neutral_on_error=True,
) -> KronosForecastSignal:
    fcast = _forecast_df(forecast_closes)
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=len(forecast_closes))
    return KronosForecastSignal(
        weight=0.25,
        _adapter=adapter,
        min_history=min_history,
        threshold_pct=threshold_pct,
        neutral_on_error=neutral_on_error,
    )


def test_bullish_forecast_scores_high():
    """Forecast +3% above current close with threshold_pct=0.02 → score == 1.0 (clamped)."""
    signal = _make_signal([103.0], threshold_pct=0.02)
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = signal.evaluate(ctx)
    assert r.name == "kronos_forecast"
    assert r.score >= 0.9


def test_threshold_scales_score():
    """Forecast exactly at threshold_pct produces score exactly 1.0."""
    signal = _make_signal([102.0], threshold_pct=0.02)
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = signal.evaluate(ctx)
    assert r.score == pytest.approx(1.0)


def test_flat_forecast_scores_zero():
    """Forecast close == current close → score == 0.0."""
    signal = _make_signal([100.0])
    ctx = MarketContext(candles=_df([100.0] * 5))
    assert signal.evaluate(ctx).score == 0.0


def test_negative_forecast_scores_zero():
    """Negative expected return is clamped to 0, not negative."""
    signal = _make_signal([98.0])
    ctx = MarketContext(candles=_df([100.0] * 5))
    assert signal.evaluate(ctx).score == 0.0


def test_insufficient_history_returns_zero():
    """Fewer candles than min_history returns score 0.0 without calling adapter."""
    fcast = _forecast_df([105.0])
    predictor = FakePredictor(fcast)
    adapter = KronosAdapter(predictor=predictor, pred_len=1)
    signal = KronosForecastSignal(weight=0.25, _adapter=adapter, min_history=10)
    ctx = MarketContext(candles=_df([100.0] * 5))  # only 5 bars < min_history=10
    r = signal.evaluate(ctx)
    assert r.score == 0.0
    assert predictor.call_count == 0


def test_forecast_none_returns_neutral_when_neutral_on_error_true():
    """adapter.forecast() → None and neutral_on_error=True → score 0.5."""
    class NonePredictor:
        def predict(self, **kwargs):
            raise RuntimeError("always fails")

    adapter = KronosAdapter(predictor=NonePredictor(), pred_len=1)
    signal = KronosForecastSignal(weight=0.25, _adapter=adapter, min_history=3, neutral_on_error=True)
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = signal.evaluate(ctx)
    assert r.score == 0.5
    assert r.meta["error"] == "no_forecast"


def test_neutral_on_error_false_returns_zero():
    """adapter.forecast() → None and neutral_on_error=False → score 0.0."""
    class NonePredictor:
        def predict(self, **kwargs):
            raise RuntimeError("always fails")

    adapter = KronosAdapter(predictor=NonePredictor(), pred_len=1)
    signal = KronosForecastSignal(weight=0.25, _adapter=adapter, min_history=3, neutral_on_error=False)
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = signal.evaluate(ctx)
    assert r.score == 0.0


def test_meta_contains_pct_change_and_forecast_close():
    """Normal result includes pct_change and forecast_close in meta."""
    signal = _make_signal([102.0])
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = signal.evaluate(ctx)
    assert "pct_change" in r.meta
    assert "forecast_close" in r.meta
    assert r.meta["forecast_close"] == pytest.approx(102.0)
