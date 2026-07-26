import pandas as pd
import pytest

from swingbot.confluence import build_signals
from swingbot.profile import StrategyProfile
from swingbot.signals.funding import FundingMeanReversionSignal
from swingbot.types import MarketContext


def _candles(n=5):
    return pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC"),
        "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0,
    })


def _ctx(values):
    extras = {"funding_8h": pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=len(values), freq="4h", tz="UTC"),
        "value": values,
    })}
    return MarketContext(candles=_candles(), extras=extras)


def test_market_context_defaults_to_no_extras():
    ctx = MarketContext(candles=_candles())
    assert ctx.extras == {}


def test_crowded_longs_score_zero():
    sig = FundingMeanReversionSignal(weight=1.0)
    assert sig.evaluate(_ctx([0.002])).score == 0.0


def test_crowded_shorts_score_one():
    sig = FundingMeanReversionSignal(weight=1.0)
    assert sig.evaluate(_ctx([-0.002])).score == 1.0


def test_midpoint_funding_scores_half():
    sig = FundingMeanReversionSignal(weight=1.0, high_thresh=0.001, low_thresh=-0.001)
    assert sig.evaluate(_ctx([0.0])).score == pytest.approx(0.5)


def test_only_the_most_recent_reading_is_used():
    sig = FundingMeanReversionSignal(weight=1.0)
    assert sig.evaluate(_ctx([-0.002, 0.002])).score == 0.0


def test_missing_series_is_neutral_and_flagged():
    sig = FundingMeanReversionSignal(weight=1.0)
    result = sig.evaluate(MarketContext(candles=_candles()))
    assert result.score == 0.5
    assert result.meta["error"] == "no_data"


def test_empty_series_is_neutral_and_flagged():
    sig = FundingMeanReversionSignal(weight=1.0)
    ctx = MarketContext(candles=_candles(),
                        extras={"funding_8h": pd.DataFrame({"ts": [], "value": []})})
    result = sig.evaluate(ctx)
    assert result.score == 0.5
    assert result.meta["error"] == "no_data"


def test_meta_carries_the_funding_reading():
    sig = FundingMeanReversionSignal(weight=1.0)
    assert sig.evaluate(_ctx([0.0003])).meta["funding_8h"] == pytest.approx(0.0003)


def test_inverted_thresholds_are_rejected_at_construction():
    with pytest.raises(ValueError):
        FundingMeanReversionSignal(weight=1.0, high_thresh=-0.001, low_thresh=0.001)


def test_build_signals_constructs_it_from_a_profile():
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "funding_mr": {"weight": 0.4, "high_thresh": 0.0006}})
    built = build_signals(profile)
    assert len(built) == 1
    assert built[0].name == "funding_mr"
    assert built[0].high_thresh == 0.0006
