from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.profiles import ProfileStore


class FakeController:
    def __init__(self): self.calls = []; self.armed_reloaded = 0
    def status(self): return {"portfolio": {"mode": "paper", "open_positions": 0},
                              "strategies": []}
    def journal(self, strategy=None): self.calls.append(("journal", strategy)); return []
    def metrics(self, strategy=None): self.calls.append(("metrics", strategy)); return {"n_trades": 0}
    def halt(self): self.calls.append("halt")
    def reset(self): self.calls.append("reset")
    def pause(self): self.calls.append("pause")
    def resume(self): self.calls.append("resume")
    def flatten(self, name=None): self.calls.append(("flatten", name))
    def set_mode(self, mode): self.calls.append(("mode", mode)); return (mode == "paper", "ok")
    def start(self): self.calls.append("start")
    def stop(self): self.calls.append("stop")
    def reload(self): self.armed_reloaded += 1


def _client(tmp_path, token="t"):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    ctrl = FakeController()
    app = create_app(controller=ctrl, profiles=profiles, creds=None, token=token)
    return TestClient(app), ctrl, profiles


def test_state_is_portfolio_shaped(tmp_path):
    c, _, _ = _client(tmp_path)
    body = c.get("/api/state").json()
    assert "portfolio" in body and "strategies" in body


def test_arm_disarm_reload_and_require_token(tmp_path):
    c, ctrl, profiles = _client(tmp_path)
    profiles.save("btc", {"symbol": "BTC/USD", "signals": {"oversold": {"weight": 1.0}},
                          "entry_threshold": 0.3})
    assert c.post("/api/strategies/arm", json={"name": "btc"}).status_code == 401
    h = {"X-Token": "t"}
    assert c.post("/api/strategies/arm", json={"name": "btc"}, headers=h).status_code == 200
    assert ctrl.armed_reloaded == 1
    assert "btc" in {s["name"] for s in c.get("/api/strategies").json() if s["armed"]}
    assert c.post("/api/strategies/disarm", json={"name": "btc"}, headers=h).status_code == 200
    assert ctrl.armed_reloaded == 2
    assert ("flatten", "btc") in ctrl.calls


def test_live_eligible_endpoint(tmp_path):
    c, _, profiles = _client(tmp_path)
    profiles.save("btc", {"symbol": "BTC/USD", "signals": {"oversold": {"weight": 1.0}},
                          "entry_threshold": 0.3})
    profiles.arm("btc")
    h = {"X-Token": "t"}
    assert c.post("/api/strategies/live-eligible",
                  json={"name": "btc", "eligible": True}, headers=h).status_code == 200
    assert profiles.is_live_eligible("btc") is True


def test_portfolio_settings_get_put(tmp_path):
    c, _, _ = _client(tmp_path)
    assert c.get("/api/portfolio/settings").json()["max_concurrent"] == 5
    r = c.put("/api/portfolio/settings", json={"max_concurrent": 9}, headers={"X-Token": "t"})
    assert r.status_code == 200 and r.json()["max_concurrent"] == 9


def test_per_strategy_flatten(tmp_path):
    c, ctrl, _ = _client(tmp_path)
    assert c.post("/api/control/btc/flatten", headers={"X-Token": "t"}).status_code == 200
    assert ("flatten", "btc") in ctrl.calls


def test_journal_metrics_strategy_filter(tmp_path):
    c, ctrl, _ = _client(tmp_path)
    c.get("/api/journal?strategy=btc"); c.get("/api/metrics?strategy=btc")
    assert ("journal", "btc") in ctrl.calls and ("metrics", "btc") in ctrl.calls
