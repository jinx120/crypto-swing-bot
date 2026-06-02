from datetime import datetime, timezone

import pandas as pd
from fastapi.testclient import TestClient

from swingbot.data.store import CandleStore
from swingbot.web import create_app


def _df(prices):
    rows = []
    for i, p in enumerate(prices):
        ts = pd.Timestamp(datetime(2024, 6, 1, tzinfo=timezone.utc)) + pd.Timedelta(minutes=15 * i)
        rows.append({"ts": ts, "open": p, "high": p + 1, "low": p - 1,
                     "close": p + 0.5, "volume": 100 + i})
    return pd.DataFrame(rows)


class _Ctl:
    def status(self): return {"mode": "paper", "running": False}
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}


class _Profiles:
    def list_armed(self): return []
    def get(self, name): return {}


class _FakeBackfiller:
    def __init__(self):
        self.ran = False

    def run(self, cfg, end_ms=None, log=print):
        self.ran = True
        return 0


def test_status_reports_coverage(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    store.upsert_df("BTC/USD", "15m", _df([10, 11, 12]))
    app = create_app(_Ctl(), _Profiles(), None, token="t", store=store)
    r = TestClient(app).get("/api/archive/status")
    assert r.status_code == 200
    body = r.json()
    entry = next(e for e in body if e["symbol"] == "BTC/USD" and e["timeframe"] == "15m")
    assert entry["count"] == 3
    assert entry["min_ts"] < entry["max_ts"]


def test_backfill_requires_token(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    bf = _FakeBackfiller()
    app = create_app(_Ctl(), _Profiles(), None, token="t", store=store, backfiller=bf)
    c = TestClient(app)
    assert c.post("/api/archive/backfill").status_code == 401
    r = c.post("/api/archive/backfill", headers={"x-token": "t"})
    assert r.status_code == 200 and r.json()["started"] is True


def test_backfill_503_when_unconfigured(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    app = create_app(_Ctl(), _Profiles(), None, token="t", store=store)  # no backfiller
    r = TestClient(app).post("/api/archive/backfill", headers={"x-token": "t"})
    assert r.status_code == 503
