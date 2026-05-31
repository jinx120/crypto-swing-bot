from fastapi.testclient import TestClient

from swingbot.web import create_app


def _bars(n=250, start=100.0):
    out, p, t0 = [], start, 1_700_000_000
    for i in range(n):
        p *= 1.001 if i % 3 else 0.999
        out.append({"time": t0 + i * 900, "open": p, "high": p * 1.01,
                    "low": p * 0.99, "close": p * 1.002, "volume": 1000 + i})
    return out


class FakeMarket:
    def get(self, symbol, timeframe, limit=500, max_age=None):
        return _bars()[-limit:]


class _Ctl:
    def status(self): return {}
    def journal(self): return []
    def metrics(self): return {}
    def halt(self): pass
    def reset(self): pass
    def pause(self): pass
    def resume(self): pass
    def flatten(self): pass
    def set_mode(self, m): return (True, "")
    def start(self): pass
    def stop(self): pass


def _client():
    app = create_app(_Ctl(), profiles=None, creds=None, token="t",
                     store=None, market=FakeMarket())
    return TestClient(app)


def test_presets_lists_archetypes():
    r = _client().get("/api/presets")
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()}
    assert keys == {"conservative", "balanced", "aggressive", "ai_kronos"}
    assert all("profile" in p for p in r.json())


def test_build_requires_token():
    c = _client()
    body = {"symbol": "TRX/USD", "risk": "balanced", "style": "swing", "ai": False}
    assert c.post("/api/strategy/build", json=body).status_code == 401


def test_build_returns_ranked_results():
    c = _client()
    body = {"symbol": "TRX/USD", "risk": "balanced", "style": "swing", "ai": False}
    r = c.post("/api/strategy/build", json=body, headers={"X-Token": "t"})
    assert r.status_code == 200
    data = r.json()
    assert data["symbol"] == "TRX/USD" and len(data["results"]) >= 1
    assert sum(1 for x in data["results"] if x["recommended"]) <= 1


def test_backtest_single_profile():
    c = _client()
    profile = {"symbol": "TRX/USD", "timeframe": "15m",
               "signals": {"oversold": {"weight": 1.0, "oversold_level": 45, "period": 14}}}
    r = c.post("/api/strategy/backtest", json={"profile": profile}, headers={"X-Token": "t"})
    assert r.status_code == 200
    assert "n_trades" in r.json()["metrics"]
