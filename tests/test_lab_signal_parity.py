"""The lab's vectorized scoring must equal the live Signal classes, bar for bar.

If this fails, a research verdict no longer describes what the live engine would
do. Fix the formulas rather than loosening the tolerance.
"""
import numpy as np
import pandas as pd
import pytest

from lab.strategy_backtest import _signal_scores
from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.profile import StrategyProfile
from swingbot.types import MarketContext

N = 400
LOOKBACK = 60


@pytest.fixture
def frames():
    rng = np.random.RandomState(7)
    ts = pd.date_range("2024-01-01", periods=N, freq="4h", tz="UTC")
    close = 100.0 * np.cumprod(1 + rng.randn(N) * 0.01)
    candles = pd.DataFrame({"ts": ts, "open": close, "high": close * 1.01,
                            "low": close * 0.99, "close": close,
                            "volume": np.abs(rng.randn(N)) + 1})
    funding = rng.randn(N) * 0.0004
    premium = rng.randn(N) * 0.001
    return candles, funding, premium


def _per_bar_scores(candles, profile, extras_arrays):
    """Score every bar the way the live engine does: one MarketContext per bar."""
    engine = ConfluenceEngine(build_signals(profile), profile)
    out = []
    for i in range(len(candles)):
        extras = {
            key: pd.DataFrame({"ts": candles["ts"].iloc[: i + 1],
                               "value": arr[: i + 1]})
            for key, arr in extras_arrays.items()
        }
        ctx = MarketContext(candles=candles.iloc[: i + 1], extras=extras)
        out.append(engine.evaluate(ctx).score)
    return np.array(out)


def test_funding_signal_matches_the_vectorized_branch(frames):
    candles, funding, _ = frames
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "funding_mr": {"weight": 1.0, "high_thresh": 0.0005, "low_thresh": -0.0001}})
    fast = _signal_scores(candles, profile, None, extras={"funding_8h": funding})
    slow = _per_bar_scores(candles, profile, {"funding_8h": funding})
    np.testing.assert_allclose(fast, slow, atol=1e-12)


def test_premium_signal_matches_the_vectorized_branch(frames):
    candles, _, premium = frames
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "premium_flow": {"weight": 1.0, "lookback": LOOKBACK, "band": 2.0}})
    fast = _signal_scores(candles, profile, None, extras={"cb_premium": premium})
    slow = _per_bar_scores(candles, profile, {"cb_premium": premium})
    np.testing.assert_allclose(fast, slow, atol=1e-12)


def test_a_blended_profile_matches_bar_for_bar(frames):
    candles, funding, premium = frames
    profile = StrategyProfile(symbol="BTC/USD", signals={
        "ema_trend": {"weight": 0.5, "fast": 8, "slow": 21, "band": 0.01},
        "funding_mr": {"weight": 0.3},
        "premium_flow": {"weight": 0.2, "lookback": LOOKBACK, "band": 2.0},
    })
    extras = {"funding_8h": funding, "cb_premium": premium}
    fast = _signal_scores(candles, profile, None, extras=extras)
    slow = _per_bar_scores(candles, profile, extras)
    # EMA warmup NaNs are handled identically on both paths; compare everything.
    np.testing.assert_allclose(fast, slow, atol=1e-12)
