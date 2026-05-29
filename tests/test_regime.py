import pandas as pd

from swingbot.profile import StrategyProfile
from swingbot.regime import RegimeFilter
from swingbot.types import MarketContext, Regime


def _df(closes):
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1.0] * n,
    })


def _profile(**kw):
    base = {"symbol": "TRX/USD", "regime_ma_period": 10}
    base.update(kw)
    return StrategyProfile.from_dict(base)


def test_uptrend_when_price_above_rising_ma():
    ctx = MarketContext(candles=_df([float(i) for i in range(1, 30)]))
    r = RegimeFilter(_profile()).evaluate(ctx)
    assert r.regime == Regime.UPTREND

def test_downtrend_when_price_below_falling_ma():
    ctx = MarketContext(candles=_df([float(i) for i in range(30, 1, -1)]))
    r = RegimeFilter(_profile()).evaluate(ctx)
    assert r.regime == Regime.DOWNTREND

def test_permits_entry_respects_allowed_regimes():
    rf = RegimeFilter(_profile())
    assert rf.permits_entry(Regime.UPTREND) is True
    assert rf.permits_entry(Regime.NEUTRAL) is True
    assert rf.permits_entry(Regime.DOWNTREND) is False

def test_uses_htf_when_present():
    # primary says down, htf says up -> regime follows htf
    ctx = MarketContext(
        candles=_df([float(i) for i in range(30, 1, -1)]),
        htf=_df([float(i) for i in range(1, 30)]),
    )
    assert RegimeFilter(_profile()).evaluate(ctx).regime == Regime.UPTREND

def test_single_row_returns_neutral():
    ctx = MarketContext(candles=_df([100.0]))
    assert RegimeFilter(_profile()).evaluate(ctx).regime == Regime.NEUTRAL
