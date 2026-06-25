import pandas as pd

from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.profile import StrategyProfile
from swingbot.types import MarketContext


def _df(closes, vols=None):
    n = len(closes)
    return pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
        "open": closes, "high": [c + 0.5 for c in closes],
        "low": [c - 0.5 for c in closes], "close": closes,
        "volume": vols if vols is not None else [1.0] * n,
    })


def _profile():
    return StrategyProfile.from_dict({
        "symbol": "TRX/USD",
        "signals": {
            "oversold": {"weight": 0.5, "oversold_level": 30, "period": 14},
            "vwap": {"weight": 0.5, "window": 20, "max_dist": 0.05},
        },
        "entry_threshold": 0.4,
    })


def test_build_signals_returns_configured_signals():
    sigs = build_signals(_profile())
    assert {s.name for s in sigs} == {"oversold", "vwap"}


def test_build_signals_strips_reserved_gate_keys():
    from swingbot.signals.oversold import OversoldSignal

    profile = StrategyProfile.from_dict({
        "symbol": "BTC/USD",
        "signals": {"oversold": {"weight": 1.0, "oversold_level": 45,
                                 "gate": True, "min_score": 0.4}},
    })
    sigs = build_signals(profile)
    assert len(sigs) == 1
    assert isinstance(sigs[0], OversoldSignal)
    assert not hasattr(sigs[0], "gate")


def test_confluence_passes_when_score_meets_threshold():
    closes = [float(i) for i in range(40, 19, -1)]   # 40..20
    ctx = MarketContext(candles=_df(closes))
    res = ConfluenceEngine(build_signals(_profile()), _profile()).evaluate(ctx)
    assert set(res.contributions) == {"oversold", "vwap"}
    assert res.score == sum(res.contributions.values())
    assert res.passed == (res.score >= res.threshold)
    assert res.threshold == 0.4

def test_confluence_fails_in_clean_uptrend():
    closes = [float(i) for i in range(1, 30)]
    ctx = MarketContext(candles=_df(closes))
    res = ConfluenceEngine(build_signals(_profile()), _profile()).evaluate(ctx)
    assert res.passed is False
