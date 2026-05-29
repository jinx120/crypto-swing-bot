import numpy as np
import pandas as pd
from swingbot.profile import StrategyProfile
from swingbot.snapshot import signal_snapshot
from swingbot.types import MarketContext


def _series(closes):
    closes = np.array(closes, dtype=float); n = len(closes)
    return pd.DataFrame({"ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
                         "open": closes, "high": closes * 1.002, "low": closes * 0.998,
                         "close": closes, "volume": np.full(n, 100.0)})


def _profile():
    return StrategyProfile.from_dict({"symbol": "TRX/USD",
        "signals": {"oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
                    "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05}},
        "entry_threshold": 0.25, "regime_ma_period": 50})


def test_snapshot_shape():
    df = _series(list(np.linspace(100, 130, 80)) + list(np.linspace(130, 118, 6)))
    snap = signal_snapshot(_profile(), MarketContext(candles=df))
    assert set(snap.keys()) >= {"regime", "permitted", "score", "threshold", "passed", "contributions", "signals"}
    assert set(snap["contributions"]) == {"oversold", "vwap"}
    assert snap["threshold"] == 0.25
    assert isinstance(snap["passed"], bool)
    assert abs(snap["score"] - sum(snap["contributions"].values())) < 1e-9
