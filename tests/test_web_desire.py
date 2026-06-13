from fastapi.testclient import TestClient

from swingbot.web import create_app


class DesireController:
    def __init__(self, start_error=None):
        self.calls = []
        self.desired = None
        self.start_error = start_error
        self._lifecycle = {"running_desired": False, "running_actual": False,
                           "startup_error": None}

    def status(self): return {}
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}

    def start(self):
        self.calls.append("start")
        if self.start_error is not None:
            raise self.start_error

    def stop(self):
        self.calls.append("stop")

    def mark_desired(self, desired):
        self.calls.append(("mark_desired", desired))
        self.desired = desired

    def lifecycle_state(self):
        return self._lifecycle


def _client(ctrl):
    return TestClient(create_app(controller=ctrl, profiles=None, creds=None, token="t"))


def test_start_marks_desired_true_after_success():
    ctrl = DesireController()
    r = _client(ctrl).post("/api/control/start", headers={"X-Token": "t"})
    assert r.status_code == 200
    assert ctrl.desired is True
    assert ctrl.calls.index("start") < ctrl.calls.index(("mark_desired", True))


def test_failed_start_does_not_mark_desired():
    ctrl = DesireController(start_error=RuntimeError("boom"))
    r = _client(ctrl).post("/api/control/start", headers={"X-Token": "t"})
    assert r.status_code == 400
    assert ctrl.desired is None
    assert ("mark_desired", True) not in ctrl.calls


def test_stop_marks_desired_false_before_stopping():
    ctrl = DesireController()
    r = _client(ctrl).post("/api/control/stop", headers={"X-Token": "t"})
    assert r.status_code == 200
    assert ctrl.desired is False
    assert ctrl.calls.index(("mark_desired", False)) < ctrl.calls.index("stop")


def test_lifecycle_endpoint_returns_state():
    ctrl = DesireController()
    r = _client(ctrl).get("/api/control/lifecycle")
    assert r.status_code == 200
    assert r.json()["running_desired"] is False
    assert "startup_error" in r.json()
