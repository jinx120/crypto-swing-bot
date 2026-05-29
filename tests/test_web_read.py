from fastapi.testclient import TestClient
from swingbot.web import create_app


class FakeController:
    def status(self): return {"mode": "paper", "running": True, "paused": False}
    def journal(self): return [{"pnl": 1.0}]
    def metrics(self): return {"n_trades": 1, "expectancy": 1.0}
    def halt(self): self.halted = True
    def reset(self): pass
    def pause(self): pass
    def resume(self): pass
    def flatten(self): pass
    def set_mode(self, mode): return (True, f"mode set to {mode}")
    def start(self): pass
    def stop(self): pass


def _client(token="tok"):
    app = create_app(controller=FakeController(), profiles=None, creds=None, token=token)
    return TestClient(app)


def test_state_ok():
    r = _client().get("/api/state")
    assert r.status_code == 200 and r.json()["mode"] == "paper"

def test_journal_and_metrics():
    c = _client()
    assert c.get("/api/journal").json() == [{"pnl": 1.0}]
    assert c.get("/api/metrics").json()["n_trades"] == 1

def test_write_requires_token():
    c = _client(token="secret")
    assert c.post("/api/control/halt").status_code == 401
    assert c.post("/api/control/halt", headers={"X-Token": "wrong"}).status_code == 401
    assert c.post("/api/control/halt", headers={"X-Token": "secret"}).status_code == 200
