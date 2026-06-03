from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.profiles import ProfileStore


class FakeController:
    def status(self): return {"portfolio": {"mode": "paper"}, "strategies": []}
    def reload(self): pass


def _client(tmp_path, token="t"):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    app = create_app(controller=FakeController(), profiles=profiles,
                     creds=None, token=token)
    return TestClient(app), profiles


def test_universe_falls_back_without_creds(tmp_path):
    c, _ = _client(tmp_path)
    body = c.get("/api/universe").json()
    assert "BTC/USD" in body["symbols"]
    assert all(s.endswith("/USD") for s in body["symbols"])


def test_watchlist_get_put_roundtrip_and_token(tmp_path):
    c, _ = _client(tmp_path)
    assert c.get("/api/watchlist").json()["symbols"] == []
    assert c.put("/api/watchlist", json={"symbols": ["ETH/USD"]}).status_code == 401
    h = {"X-Token": "t"}
    r = c.put("/api/watchlist", json={"symbols": ["ETH/USD", "BTC/USD"]}, headers=h)
    assert r.status_code == 200
    assert c.get("/api/watchlist").json()["symbols"] == ["ETH/USD", "BTC/USD"]
