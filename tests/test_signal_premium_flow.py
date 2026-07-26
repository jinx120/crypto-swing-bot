import numpy as np
import pandas as pd
import pytest

from swingbot.confluence import build_signals
from swingbot.profile import StrategyProfile
from swingbot.signals.premium_flow import PremiumFlowSignal
from swingbot.types import MarketContext


def _candles(n=5):
    return pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC"),
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0,
    })


def _ctx(values):
    return MarketContext(candles=_candles(), extras={"cb_premium": pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=len(values), freq="4h", tz="UTC"),
        "value": values,
    })})


def test_premium_far_above_its_own_mean_scores_one():
    values = list(np.zeros(29)) + [10.0]
    assert PremiumFlowSignal(weight=1.0, lookback=30).evaluate(_ctx(values)).score == 1.0


def test_premium_far_below_its_own_mean_scores_zero():
    values = list(np.zeros(29)) + [-10.0]
    assert PremiumFlowSignal(weight=1.0, lookback=30).evaluate(_ctx(values)).score == 0.0


def test_premium_at_its_own_mean_scores_half():
    values = [0.001, -0.001] * 15
    sig = PremiumFlowSignal(weight=1.0, lookback=30)
    assert sig.evaluate(_ctx(values + [0.0])).score == pytest.approx(0.5, abs=0.05)


def test_score_uses_only_the_trailing_lookback_window():
    # a huge old premium outside the window must not move today's z-score
    values = [50.0] + list(np.zeros(29)) + [0.0]
    sig = PremiumFlowSignal(weight=1.0, lookback=30)
    assert sig.evaluate(_ctx(values)).score == pytest.approx(0.5, abs=0.05)


def test_short_history_is_neutral_and_flagged():
    result = PremiumFlowSignal(weight=1.0, lookback=30).evaluate(_ctx([0.001] * 5))
    assert result.score == 0.5
    assert result.meta["error"] == "insufficient_history"


def test_a_flat_series_is_neutral_rather_than_dividing_by_zero():
    result = PremiumFlowSignal(weight=1.0, lookback=30).evaluate(_ctx([0.001] * 40))
    assert result.score == 0.5
    assert result.meta["error"] == "zero_variance"


def test_missing_series_is_neutral_and_flagged():
    result = PremiumFlowSignal(weight=1.0).evaluate(MarketContext(candles=_candles()))
    assert result.score == 0.5
    assert result.meta["error"] == "no_data"


def test_meta_carries_the_premium_and_its_z_score():
    values = list(np.zeros(29)) + [1.0]
    meta = PremiumFlowSignal(weight=1.0, lookback=30).evaluate(_ctx(values)).meta
    assert meta["cb_premium"] == 1.0
    assert meta["z"] > 2.0


def test_nonpositive_band_is_rejected_at_construction():
    with pytest.raises(ValueError):
        PremiumFlowSignal(weight=1.0, band=0.0)


def test_build_signals_constructs_it_from_a_profile():
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "premium_flow": {"weight": 0.3, "lookback": 90, "band": 1.5}})
    built = build_signals(profile)
    assert built[0].name == "premium_flow"
    assert built[0].lookback == 90
    assert built[0].band == 1.5
