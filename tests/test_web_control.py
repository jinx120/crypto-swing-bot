from fastapi.testclient import TestClient
from swingbot.web import create_app


class RecordingController:
    def __init__(self): self.calls = []
    def status(self): return {}
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}
    def halt(self): self.calls.append("halt")
    def reset(self): self.calls.append("reset")
    def pause(self): self.calls.append("pause")
    def resume(self): self.calls.append("resume")
    def flatten(self, name=None): self.calls.append(("flatten", name))
    def reload(self): self.calls.append("reload")
    def set_mode(self, mode): self.calls.append(("mode", mode)); return (mode == "paper", "live blocked" if mode == "live" else "ok")
    def start(self): self.calls.append("start")
    def stop(self): self.calls.append("stop")


def _client():
    ctrl = RecordingController()
    return TestClient(create_app(controller=ctrl, profiles=None, creds=None, token="t")), ctrl


def test_control_actions_invoke_controller():
    c, ctrl = _client(); h = {"X-Token": "t"}
    for action in ("reset", "pause", "resume", "flatten"):
        assert c.post(f"/api/control/{action}", headers=h).status_code == 200
    assert {"reset", "pause", "resume"} <= set(ctrl.calls)
    assert ("flatten", None) in ctrl.calls

def test_mode_switch_returns_gate_result():
    c, _ = _client(); h = {"X-Token": "t"}
    assert c.post("/api/control/mode", json={"mode": "paper"}, headers=h).json()["ok"] is True
    r = c.post("/api/control/mode", json={"mode": "live"}, headers=h)
    assert r.json()["ok"] is False and "blocked" in r.json()["reason"]

def test_start_stop_invoke_controller():
    c, ctrl = _client(); h = {"X-Token": "t"}
    assert c.post("/api/control/start", headers=h).status_code == 200
    assert c.post("/api/control/stop", headers=h).status_code == 200
    assert "start" in ctrl.calls and "stop" in ctrl.calls

def test_start_surfaces_error_as_400():
    class FailingStartController(RecordingController):
        def start(self): raise RuntimeError("no active strategy profile set")

    ctrl = FailingStartController()
    c = TestClient(create_app(controller=ctrl, profiles=None, creds=None, token="t"))
    r = c.post("/api/control/start", headers={"X-Token": "t"})
    assert r.status_code == 400
    assert "no active strategy profile" in r.json()["detail"]

def test_start_requires_token():
    c, _ = _client()
    assert c.post("/api/control/start").status_code == 401

def test_control_requires_token():
    c, _ = _client()
    assert c.post("/api/control/pause").status_code == 401
