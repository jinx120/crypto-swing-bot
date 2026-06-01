from datetime import datetime, timezone

import pandas as pd
from fastapi.testclient import TestClient

from swingbot.data.store import CandleStore
from swingbot.web import create_app


def _df(prices):
    rows = []
    for i, p in enumerate(prices):
        ts = pd.Timestamp(datetime(2024, 1, 1, tzinfo=timezone.utc)) + pd.Timedelta(minutes=15 * i)
        rows.append({"ts": ts, "open": p, "high": p + 1, "low": p - 1,
                     "close": p + 0.5, "volume": 100 + i})
    return pd.DataFrame(rows)


def test_upsert_and_get_roundtrip(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    n = store.upsert_df("TRX/USD", "15m", _df([10, 11, 12]))
    assert n == 3
    bars = store.get("TRX/USD", "15m")
    assert len(bars) == 3
    # oldest-first, epoch seconds, lightweight-charts shape
    assert bars[0]["time"] < bars[-1]["time"]
    assert set(bars[0]) == {"time", "open", "high", "low", "close", "volume"}
    assert bars[0]["open"] == 10


def test_upsert_is_idempotent(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    store.upsert_df("TRX/USD", "15m", _df([10, 11, 12]))
    store.upsert_df("TRX/USD", "15m", _df([10, 11, 12]))  # same bars again
    assert len(store.get("TRX/USD", "15m")) == 3  # no duplicates


def test_get_limit_returns_most_recent(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    store.upsert_df("TRX/USD", "15m", _df(list(range(20))))
    bars = store.get("TRX/USD", "15m", limit=5)
    assert len(bars) == 5
    assert bars[-1]["open"] == 19  # newest bar present
    assert bars[0]["open"] == 15   # only the last 5


class _FakeController:
    def status(self): return {"mode": "paper", "running": False}
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}
    def halt(self): pass
    def reset(self): pass
    def pause(self): pass
    def resume(self): pass
    def flatten(self, name=None): pass
    def reload(self): pass
    def set_mode(self, mode): return (True, "")
    def start(self): pass
    def stop(self): pass


class _FakeProfiles:
    def list_armed(self): return ["trx"]
    def get(self, name): return {"symbol": "TRX/USD", "timeframe": "15m"}


def test_candles_endpoint_serves_store(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    store.upsert_df("TRX/USD", "15m", _df([10, 11, 12]))
    app = create_app(_FakeController(), _FakeProfiles(), None, token="t", store=store)
    c = TestClient(app)
    r = c.get("/api/candles")  # no params -> active profile
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "TRX/USD" and body["timeframe"] == "15m"
    assert len(body["candles"]) == 3


def test_candles_endpoint_without_store_returns_empty():
    app = create_app(_FakeController(), _FakeProfiles(), None, token="t")
    c = TestClient(app)
    r = c.get("/api/candles")
    assert r.status_code == 200 and r.json()["candles"] == []
