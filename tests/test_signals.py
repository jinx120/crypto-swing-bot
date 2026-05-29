import pandas as pd

from swingbot.types import MarketContext
from swingbot.signals.oversold import OversoldSignal
from swingbot.signals.vwap import VwapSignal
from swingbot.signals.relative_strength import RelativeStrengthSignal
from swingbot.signals.fvg import FvgSignal


def _df(closes, highs=None, lows=None, vols=None):
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes,
        "high": highs if highs is not None else [c + 0.5 for c in closes],
        "low": lows if lows is not None else [c - 0.5 for c in closes],
        "close": closes,
        "volume": vols if vols is not None else [100.0] * n,
    })


def test_oversold_high_when_falling():
    ctx = MarketContext(candles=_df([float(i) for i in range(40, 1, -1)]))
    r = OversoldSignal(weight=0.4, oversold_level=30).evaluate(ctx)
    assert r.name == "oversold"
    assert r.score > 0.9

def test_oversold_zero_when_rising():
    ctx = MarketContext(candles=_df([float(i) for i in range(1, 40)]))
    assert OversoldSignal(weight=0.4, oversold_level=30).evaluate(ctx).score == 0.0

def test_vwap_high_when_price_below_vwap():
    closes = [100.0] * 20 + [90.0]
    ctx = MarketContext(candles=_df(closes, vols=[1.0] * 21))
    r = VwapSignal(weight=0.3, window=20, max_dist=0.05).evaluate(ctx)
    assert r.score > 0.0

def test_vwap_zero_when_price_above_vwap():
    closes = [100.0] * 20 + [110.0]
    ctx = MarketContext(candles=_df(closes, vols=[1.0] * 21))
    assert VwapSignal(weight=0.3, window=20, max_dist=0.05).evaluate(ctx).score == 0.0

def test_relative_strength_high_when_outperforming():
    coin = _df([100.0, 110.0])
    bench = _df([100.0, 100.0])
    ctx = MarketContext(candles=coin, benchmark=bench)
    r = RelativeStrengthSignal(weight=0.3, band=0.05, lookback=1).evaluate(ctx)
    assert r.score > 0.9

def test_relative_strength_neutral_without_benchmark():
    ctx = MarketContext(candles=_df([100.0, 110.0]), benchmark=None)
    assert RelativeStrengthSignal(weight=0.3, band=0.05, lookback=1).evaluate(ctx).score == 0.5

def test_fvg_stub_returns_neutral_zero():
    ctx = MarketContext(candles=_df([100.0] * 5))
    r = FvgSignal(weight=0.0).evaluate(ctx)
    assert r.name == "fvg"
    assert r.score == 0.0
