from datetime import datetime, timezone

import pandas as pd

from swingbot.data.market import MarketData
from swingbot.data.store import CandleStore


def _df(prices, start=None):
    start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i, p in enumerate(prices):
        ts = pd.Timestamp(start) + pd.Timedelta(minutes=15 * i)
        rows.append({"ts": ts, "open": p, "high": p + 1, "low": p - 1,
                     "close": p + 0.5, "volume": 100 + i})
    return pd.DataFrame(rows)


class _FakeMultiProvider:
    def __init__(self, dfs):
        self.dfs = dfs            # {symbol: df}
        self.multi_calls = 0
    def get_candles_multi(self, symbols, timeframe, lookback):
        self.multi_calls += 1
        return {s: self.dfs[s] for s in symbols if s in self.dfs}


def test_refresh_many_upserts_each_symbol(tmp_path, monkeypatch):
    store = CandleStore(str(tmp_path / "c.db"))
    md = MarketData(store, creds=None)
    prov = _FakeMultiProvider({"BTC/USD": _df([10, 11, 12]), "ETH/USD": _df([20, 21])})
    monkeypatch.setattr(md, "_provider", lambda: prov)

    n = md.refresh_many(["BTC/USD", "ETH/USD"], "15m")
    assert prov.multi_calls == 1          # one batched fetch
    assert n == 5                          # 3 + 2 bars upserted
    assert len(store.get("BTC/USD", "15m")) == 3
    assert len(store.get("ETH/USD", "15m")) == 2
