from fastapi.testclient import TestClient

from swingbot.web import create_app


class _Ctl:
    def status(self): return {}
    def journal(self, s=None): return []
    def metrics(self, s=None): return {}
    def readiness(self): return {}
    def trading_health(self): return {}


class _FakeService:
    def backtest(self): return {"ema": {"n_trades": 1}, "kronos": {"n_trades": 2}}
    def position(self): return None
    def trades(self, limit=50): return []
    def journal(self, limit=50): return []
    def candles(self, limit=200): return []


def test_auto_routes_mounted_when_service_provided():
    app = create_app(controller=_Ctl(), profiles=None, creds=None,
                     token="t", auto_dashboard=_FakeService())
    c = TestClient(app)
    assert c.get("/api/backtest/kronos").json()["n_trades"] == 2
    assert c.get("/api/live/position").json() is None


def test_auto_routes_absent_when_no_service():
    app = create_app(controller=_Ctl(), profiles=None, creds=None, token="t")
    assert TestClient(app).get("/api/backtest/ema").status_code == 404
