from fastapi.testclient import TestClient

from swingbot.web import create_app


class DesireController:
    def __init__(self, start_error=None, stop_error=None):
        self.calls = []
        self.start_error = start_error
        self.stop_error = stop_error
        self._lifecycle = {"running_desired": False, "running_actual": False,
                           "startup_error": None}

    def status(self): return {}
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}

    def request_start(self):
        self.calls.append("request_start")
        if self.start_error is not None:
            raise self.start_error

    def request_stop(self):
        self.calls.append("request_stop")
        if self.stop_error is not None:
            raise self.stop_error

    def lifecycle_state(self):
        return self._lifecycle


def _client(ctrl):
    return TestClient(create_app(controller=ctrl, profiles=None, creds=None, token="t"))


def test_start_routes_to_serialized_request_start():
    ctrl = DesireController()
    r = _client(ctrl).post("/api/control/start", headers={"X-Token": "t"})
    assert r.status_code == 200
    assert ctrl.calls == ["request_start"]


def test_failed_request_start_surfaces_400():
    ctrl = DesireController(start_error=RuntimeError("boom"))
    r = _client(ctrl).post("/api/control/start", headers={"X-Token": "t"})
    assert r.status_code == 400
    assert "boom" in r.json()["detail"]


def test_stop_routes_to_serialized_request_stop():
    ctrl = DesireController()
    r = _client(ctrl).post("/api/control/stop", headers={"X-Token": "t"})
    assert r.status_code == 200
    assert ctrl.calls == ["request_stop"]


def test_lifecycle_endpoint_returns_state():
    ctrl = DesireController()
    r = _client(ctrl).get("/api/control/lifecycle")
    assert r.status_code == 200
    assert r.json()["running_desired"] is False
    assert "startup_error" in r.json()


def test_lifecycle_endpoint_exposes_unreadable_desire():
    ctrl = DesireController()
    ctrl._lifecycle = {
        "mode": "paper", "running_flag": False, "thread_alive": False,
        "running_actual": False, "running_desired": None,
        "running_desired_error": "runtime-state read failed",
        "paused": False, "halted": False,
        "startup_error": "auto-start failed: runtime-state read failed",
    }
    r = _client(ctrl).get("/api/control/lifecycle")
    assert r.status_code == 200
    body = r.json()
    assert body["running_desired"] is None
    assert body["running_desired_error"] == "runtime-state read failed"
    assert "runtime-state read failed" in body["startup_error"]


def test_stop_timeout_returns_500_not_ok():
    from swingbot.supervisor import LifecycleError
    ctrl = DesireController(stop_error=LifecycleError(
        "stop timed out; loop thread still alive", stop_timed_out=True))
    r = _client(ctrl).post("/api/control/stop", headers={"X-Token": "t"})
    assert r.status_code == 500
    assert r.json() != {"ok": True}
    assert "still alive" in r.json()["detail"]


def test_start_persist_failure_returns_500():
    from swingbot.supervisor import DesirePersistError
    ctrl = DesireController(start_error=DesirePersistError(
        "started loop but failed to persist running_desired=true: disk full; "
        "loop rolled back", rolled_back=True))
    r = _client(ctrl).post("/api/control/start", headers={"X-Token": "t"})
    assert r.status_code == 500
    assert "rolled back" in r.json()["detail"]


def test_start_precondition_error_still_returns_400():
    ctrl = DesireController(start_error=RuntimeError("previous loop thread still alive"))
    r = _client(ctrl).post("/api/control/start", headers={"X-Token": "t"})
    assert r.status_code == 400
