from fastapi import FastAPI
from fastapi.testclient import TestClient

from swingbot.autodash.router import build_auto_router


class _FakeService:
    def backtest(self):
        return {"ema": {"n_trades": 3, "win_rate": 0.66},
                "kronos": {"n_trades": 4, "win_rate": 0.5}}
    def position(self):
        return {"symbol": "BTC/USD", "entry_price": 65000.0, "qty": 0.01}
    def trades(self, limit=50):
        return [{"ts": "2026-06-17T18:30:00+00:00", "pnl": 5.0,
                 "won": True, "reason": "tp"}]
    def journal(self, limit=50):
        return [{"ts": "t", "kind": "decision", "symbol": "BTC/USD",
                 "reason": "hold", "payload": {}}]
    def candles(self, limit=200):
        return [{"time": 1781265600, "open": 1, "high": 2, "low": 0,
                 "close": 1.5, "volume": 1}]


def _client():
    app = FastAPI()
    app.include_router(build_auto_router(_FakeService()))
    return TestClient(app)


def test_backtest_ema_and_kronos():
    c = _client()
    assert c.get("/api/backtest/ema").json()["win_rate"] == 0.66
    assert c.get("/api/backtest/kronos").json()["n_trades"] == 4


def test_live_endpoints_shapes():
    c = _client()
    assert c.get("/api/live/position").json()["entry_price"] == 65000.0
    assert c.get("/api/live/trades").json()[0]["pnl"] == 5.0
    assert c.get("/api/live/journal").json()[0]["kind"] == "decision"
    assert c.get("/api/live/candles").json()[0]["time"] == 1781265600
