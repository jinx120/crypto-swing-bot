import pandas as pd

from swingbot.types import MarketContext
from swingbot.signals.ema_trend import EmaTrendSignal
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


def _ctx(closes):
    df = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=len(closes), freq="15min", tz="UTC"),
        "open": closes,
        "high": closes,
        "low": closes,
        "close": closes,
        "volume": [1.0] * len(closes),
    })
    return MarketContext(candles=df)


def test_ema_trend_strong_uptrend_scores_high():
    closes = [float(x) for x in range(1, 61)]
    sig = EmaTrendSignal(weight=1.0, fast=12, slow=26, band=0.01)
    r = sig.evaluate(_ctx(closes))
    assert r.name == "ema_trend"
    assert r.score >= 0.9
    assert r.meta["spread"] > 0


def test_ema_trend_downtrend_scores_zero():
    closes = [float(x) for x in range(60, 0, -1)]
    sig = EmaTrendSignal(weight=1.0, fast=12, slow=26, band=0.01)
    r = sig.evaluate(_ctx(closes))
    assert r.score == 0.0


def test_ema_trend_warmup_scores_zero():
    closes = [10.0, 11.0, 12.0]
    sig = EmaTrendSignal(weight=1.0, fast=12, slow=26, band=0.01)
    r = sig.evaluate(_ctx(closes))
    assert r.score == 0.0
    assert r.meta["ema_fast"] is None


# --- FVG (ICT fair value gap) ---------------------------------------------
# A bullish FVG is a 3-candle imbalance: low[3] > high[1], leaving an
# un-traded gap [high[1], low[3]]. The signal scores the discount long entry:
# high when price has retraced DOWN into the gap (deeper = stronger), zero
# when price hasn't retraced yet (above the gap) or has broken below it.

def _fvg_df(highs, lows, closes):
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes, "high": highs, "low": lows, "close": closes,
        "volume": [100.0] * n,
    })

# gap forms at candles 0-1-2: gap_low=high[0]=100, gap_high=low[2]=103
_FVG_HIGHS = [100.0, 108.0, 110.0, 109.0, 106.0, 103.0]
_FVG_LOWS  = [98.0, 104.0, 103.0, 102.0, 101.0, 100.5]

def test_fvg_name():
    ctx = MarketContext(candles=_df([100.0] * 5))
    assert FvgSignal(weight=0.0).evaluate(ctx).name == "fvg"

def test_fvg_warmup_returns_zero():
    ctx = MarketContext(candles=_df([100.0, 101.0]))
    assert FvgSignal(weight=0.3).evaluate(ctx).score == 0.0

def test_fvg_no_gap_returns_zero():
    # flat candles never open a gap
    ctx = MarketContext(candles=_df([100.0] * 6, highs=[100.5] * 6, lows=[99.5] * 6))
    assert FvgSignal(weight=0.3).evaluate(ctx).score == 0.0

def test_fvg_scores_when_price_retraces_into_gap():
    # last close 101 sits inside the [100, 103] gap
    closes = [99.0, 107.0, 104.0, 105.0, 102.0, 101.0]
    ctx = MarketContext(candles=_fvg_df(_FVG_HIGHS, _FVG_LOWS, closes))
    r = FvgSignal(weight=0.3).evaluate(ctx)
    assert 0.6 < r.score < 0.72            # (103-101)/(103-100) = 0.667
    assert r.meta["gap_low"] == 100.0 and r.meta["gap_high"] == 103.0

def test_fvg_deeper_retrace_scores_higher():
    closes = [99.0, 107.0, 104.0, 105.0, 102.0, 100.2]
    ctx = MarketContext(candles=_fvg_df(_FVG_HIGHS, _FVG_LOWS, closes))
    assert FvgSignal(weight=0.3).evaluate(ctx).score > 0.9   # near gap floor

def test_fvg_zero_when_price_above_gap():
    # no retrace yet — price still above gap_high
    closes = [99.0, 107.0, 104.0, 105.0, 106.0, 104.0]
    ctx = MarketContext(candles=_fvg_df(_FVG_HIGHS, _FVG_LOWS, closes))
    assert FvgSignal(weight=0.3).evaluate(ctx).score == 0.0

def test_fvg_zero_when_price_below_gap_invalidated():
    closes = [99.0, 107.0, 104.0, 105.0, 102.0, 99.0]
    ctx = MarketContext(candles=_fvg_df(_FVG_HIGHS, _FVG_LOWS, closes))
    assert FvgSignal(weight=0.3).evaluate(ctx).score == 0.0

def test_fvg_min_gap_pct_filters_tiny_gaps():
    # tiny gap (~0.1%) filtered out when min_gap_pct = 0.5%
    highs = [100.0, 101.0, 102.0, 101.5, 101.0, 100.6]
    lows  = [99.5, 100.5, 100.1, 100.05, 100.02, 100.05]
    closes = [99.8, 100.8, 100.2, 100.3, 100.1, 100.08]
    ctx = MarketContext(candles=_fvg_df(highs, lows, closes))
    assert FvgSignal(weight=0.3, min_gap_pct=0.005).evaluate(ctx).score == 0.0
