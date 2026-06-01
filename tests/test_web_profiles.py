from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.profiles import ProfileStore


class FakeController:
    def status(self): return {}
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}
    def halt(self): pass
    def reset(self): pass
    def pause(self): pass
    def resume(self): pass
    def flatten(self, name=None): pass
    def reload(self): pass
    def set_mode(self, m): return (True, "")
    def start(self): pass
    def stop(self): pass


def _client(tmp_path, token="tok"):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    app = create_app(controller=FakeController(), profiles=profiles, creds=None, token=token)
    return TestClient(app), profiles


def test_profile_crud_and_arm(tmp_path):
    c, _ = _client(tmp_path)
    h = {"X-Token": "tok"}
    body = {"name": "trx", "profile": {"symbol": "TRX/USD",
            "signals": {"oversold": {"weight": 1.0}}, "entry_threshold": 0.3}}
    assert c.post("/api/profiles", json=body, headers=h).status_code == 200
    assert "trx" in c.get("/api/profiles").json()
    assert c.post("/api/strategies/arm", json={"name": "trx"}, headers=h).status_code == 200
    armed = [s for s in c.get("/api/strategies").json() if s["armed"]]
    assert any(s["name"] == "trx" for s in armed)

def test_profile_create_requires_token(tmp_path):
    c, _ = _client(tmp_path)
    body = {"name": "x", "profile": {"symbol": "TRX/USD", "signals": {}}}
    assert c.post("/api/profiles", json=body).status_code == 401

def test_invalid_profile_rejected(tmp_path):
    c, _ = _client(tmp_path)
    body = {"name": "bad", "profile": {"signals": {}}}
    assert c.post("/api/profiles", json=body, headers={"X-Token": "tok"}).status_code == 400


def test_get_profile_by_name(tmp_path):
    c, _ = _client(tmp_path)
    h = {"X-Token": "tok"}
    body = {"name": "trx", "profile": {"symbol": "TRX/USD",
            "signals": {"oversold": {"weight": 1.0}}, "entry_threshold": 0.3}}
    c.post("/api/profiles", json=body, headers=h)
    r = c.get("/api/profiles/trx")
    assert r.status_code == 200 and r.json()["profile"]["symbol"] == "TRX/USD"
    assert c.get("/api/profiles/nope").status_code == 404
