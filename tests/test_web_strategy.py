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


def test_strategies_list_generic_fields():
    class FakeProfiles:
        def list(self):
            return ["btc_trend", "my_custom"]

        def get(self, name):
            return {
                "symbol": {
                    "btc_trend": "BTC/USD",
                    "my_custom": "ETH/USD",
                }[name],
            }

        def armed_with_flags(self):
            return [{"name": "btc_trend", "live_eligible": True}]

    app = create_app(
        _Ctl(), profiles=FakeProfiles(), creds=None, token="t",
        store=None, market=FakeMarket(),
    )
    rows = {r["name"]: r for r in TestClient(app).get("/api/strategies").json()}
    assert rows["btc_trend"]["symbol"] == "BTC/USD"
    assert rows["btc_trend"]["armed"] is True
    assert rows["btc_trend"]["live_eligible"] is True
    assert rows["my_custom"]["symbol"] == "ETH/USD"
    assert rows["my_custom"]["armed"] is False
