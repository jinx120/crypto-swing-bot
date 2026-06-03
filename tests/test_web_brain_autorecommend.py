import time
from fastapi.testclient import TestClient

from swingbot.web import create_app


class _Ctl:
    def status(self): return {"portfolio": {}, "strategies": []}
    def reload(self): pass


class FakeProfiles:
    def __init__(self, auto): self._auto = auto
    def get_watchlist(self): return ["BTC/USD"]
    def get_portfolio_settings(self): return {"brain_auto_recommend": self._auto}


class FakeDiscovery:
    def sweep(self, symbols, window_key="full", max_symbols=50): return []


class FakeBrain:
    def __init__(self): self.calls = []
    def recommend(self, source="manual"): self.calls.append(source)


def _client(auto):
    brain = FakeBrain()
    app = create_app(_Ctl(), profiles=FakeProfiles(auto), creds=None, token="t",
                     discovery=FakeDiscovery(), brain=brain)
    return TestClient(app), brain


def _wait(brain):
    for _ in range(50):
        if brain.calls: return
        time.sleep(0.02)


def test_auto_recommend_fires_after_sweep_when_enabled():
    client, brain = _client(auto=True)
    client.post("/api/discovery/refresh", headers={"x-token": "t"},
                json={"scope": "watchlist"})
    _wait(brain)
    assert brain.calls == ["auto-after-discovery"]


def test_auto_recommend_silent_when_disabled():
    client, brain = _client(auto=False)
    client.post("/api/discovery/refresh", headers={"x-token": "t"},
                json={"scope": "watchlist"})
    time.sleep(0.3)
    assert brain.calls == []
