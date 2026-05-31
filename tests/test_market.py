from datetime import datetime, timezone

import pandas as pd

from swingbot.data.market import MarketData, timeframe_seconds
from swingbot.data.store import CandleStore


def _df(prices, start=None):
    start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i, p in enumerate(prices):
        ts = pd.Timestamp(start) + pd.Timedelta(minutes=15 * i)
        rows.append({"ts": ts, "open": p, "high": p + 1, "low": p - 1,
                     "close": p + 0.5, "volume": 100 + i})
    return pd.DataFrame(rows)


class _FakeProvider:
    def __init__(self, df):
        self.df = df
        self.calls = 0

    def get_candles(self, symbol, timeframe, lookback):
        self.calls += 1
        return self.df


def test_timeframe_seconds():
    assert timeframe_seconds("1m") == 60
    assert timeframe_seconds("15m") == 900
    assert timeframe_seconds("4h") == 14400
    assert timeframe_seconds("1d") == 86400
    assert timeframe_seconds("garbage") == 900  # safe default


def test_get_fetches_on_empty_store(tmp_path, monkeypatch):
    store = CandleStore(str(tmp_path / "c.db"))
    md = MarketData(store, creds=None)
    prov = _FakeProvider(_df([10, 11, 12]))
    monkeypatch.setattr(md, "_provider", lambda: prov)

    bars = md.get("TRX/USD", "15m", limit=500, max_age=900)
    assert prov.calls == 1            # store was empty -> fetched
    assert len(bars) == 3


def test_get_serves_cache_when_fresh(tmp_path, monkeypatch):
    store = CandleStore(str(tmp_path / "c.db"))
    # seed with bars timestamped "now" so they are not stale
    md = MarketData(store, creds=None)
    fresh = _df([10, 11, 12], start=datetime.now(timezone.utc) - pd.Timedelta(minutes=30).to_pytimedelta())
    store.upsert_df("TRX/USD", "15m", fresh)
    prov = _FakeProvider(_df([99]))
    monkeypatch.setattr(md, "_provider", lambda: prov)

    bars = md.get("TRX/USD", "15m", limit=500, max_age=86400)
    assert prov.calls == 0            # fresh enough -> no fetch
    assert len(bars) == 3


def test_get_without_creds_returns_store_only(tmp_path):
    store = CandleStore(str(tmp_path / "c.db"))
    md = MarketData(store, creds=None)   # _provider() -> None
    assert md.get("TRX/USD", "15m") == []   # nothing cached, can't fetch
