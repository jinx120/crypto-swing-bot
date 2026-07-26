import numpy as np
import pandas as pd
import pytest

from lab.strategy_backtest import _signal_scores
from swingbot.profile import StrategyProfile


def _df(n=300):
    ts = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    close = np.linspace(100.0, 200.0, n)
    return pd.DataFrame({"ts": ts, "open": close, "high": close + 1,
                         "low": close - 1, "close": close, "volume": np.ones(n)})


def test_funding_mr_scores_one_at_or_below_the_low_threshold():
    df = _df(10)
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "funding_mr": {"weight": 1.0, "high_thresh": 0.0005, "low_thresh": -0.0001}})
    extras = {"funding_8h": np.full(10, -0.0005)}  # deeply negative -> crowded short
    assert _signal_scores(df, profile, None, extras=extras).tolist() == [1.0] * 10


def test_funding_mr_scores_zero_at_or_above_the_high_threshold():
    df = _df(10)
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "funding_mr": {"weight": 1.0, "high_thresh": 0.0005, "low_thresh": -0.0001}})
    extras = {"funding_8h": np.full(10, 0.002)}  # crowded long -> no new longs
    assert _signal_scores(df, profile, None, extras=extras).tolist() == [0.0] * 10


def test_funding_mr_is_neutral_where_the_series_has_no_reading():
    df = _df(3)
    profile = StrategyProfile(symbol="BTC/USD", signals={"funding_mr": {"weight": 1.0}})
    extras = {"funding_8h": np.array([np.nan, np.nan, -0.001])}
    assert _signal_scores(df, profile, None, extras=extras).tolist() == [0.5, 0.5, 1.0]


def test_premium_flow_scores_high_when_premium_is_far_above_its_own_mean():
    df = _df(60)
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "premium_flow": {"weight": 1.0, "lookback": 20, "band": 2.0}})
    series = np.concatenate([np.zeros(59), [10.0]])  # last bar is a huge positive z
    scores = _signal_scores(df, profile, None, extras={"cb_premium": series})
    assert scores[-1] == 1.0


def test_premium_flow_is_neutral_during_its_warmup():
    df = _df(60)
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "premium_flow": {"weight": 1.0, "lookback": 20, "band": 2.0}})
    scores = _signal_scores(df, profile, None,
                            extras={"cb_premium": np.random.RandomState(0).randn(60)})
    assert scores[:19].tolist() == [0.5] * 19


def test_premium_flow_flat_window_is_neutral_in_the_vectorized_path():
    df = _df(60)
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "premium_flow": {"weight": 1.0, "lookback": 20, "band": 2.0}})
    scores = _signal_scores(df, profile, None, extras={"cb_premium": np.full(60, 0.001)})
    assert scores[-1] == 0.5


def test_a_signal_that_needs_extras_fails_loudly_when_they_are_absent():
    df = _df(10)
    profile = StrategyProfile(symbol="BTC/USD", signals={"funding_mr": {"weight": 1.0}})
    with pytest.raises(ValueError, match="funding_mr"):
        _signal_scores(df, profile, None)
