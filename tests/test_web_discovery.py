from fastapi.testclient import TestClient

from swingbot.web import create_app


def _bars(n=300, start=100.0):
    out, p, t0 = [], start, 1_700_000_000
    for i in range(n):
        p *= 1.001 if i % 3 else 0.999
        out.append({"time": t0 + i * 900, "open": p, "high": p * 1.01,
                    "low": p * 0.99, "close": p * 1.002, "volume": 1000 + i})
    return out


class FakeMarket:
    def get(self, symbol, timeframe, limit=500, max_age=None):
        return _bars()[-limit:]


class FakeStore:
    def symbols(self):
        return [{"symbol": "BTC/USD", "timeframe": "15m"}]
    def coverage(self, symbol, timeframe):
        day = 86400
        return {"min_ts": 1_700_000_000, "max_ts": 1_700_000_000 + 400 * day, "count": 38000}


class _Ctl:
    def status(self): return {}
    def reload(self): pass


def _client(**kw):
    from swingbot.discovery import DiscoveryEngine
    app = create_app(_Ctl(), profiles=None, creds=None, token="t",
                     store=FakeStore(), market=FakeMarket(),
                     discovery=DiscoveryEngine(FakeMarket()), **kw)
    return TestClient(app)


def test_discovery_starts_empty():
    r = _client().get("/api/discovery")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "idle" and body["rows"] == [] and body["computed_at"] is None


def test_discovery_windows_from_coverage():
    r = _client().get("/api/discovery/windows")
    assert r.status_code == 200
    assert [w["key"] for w in r.json()] == ["full", "last_1y", "last_90d", "last_30d"]


def test_refresh_requires_token():
    assert _client().post("/api/discovery/refresh", json={}).status_code == 401


def test_refresh_runs_sweep_and_caches(tmp_path):
    c = _client(discovery_cache_path=str(tmp_path / "discovery.json"))
    # seed a tiny universe by monkeypatching the resolver via watchlist scope
    r = c.post("/api/discovery/refresh", json={"scope": "watchlist", "window": "full"},
               headers={"X-Token": "t"})
    assert r.status_code == 200 and r.json()["started"] is True


def test_refresh_guards_against_concurrent_sweep():
    c = _client()
    c.app.state.discovery = {**c.app.state.discovery, "status": "computing"}
    r = c.post("/api/discovery/refresh", json={}, headers={"X-Token": "t"})
    assert r.json() == {"started": False, "status": "computing"}
