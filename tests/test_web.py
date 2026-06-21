from fastapi.testclient import TestClient

from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class FakeController:
    def __init__(self):
        self.reloaded = 0

    def status(self):
        return {"portfolio": {"mode": "paper", "open_positions": 0}, "strategies": []}

    def journal(self, strategy=None):
        return []

    def metrics(self, strategy=None):
        return {"n_trades": 0}

    def halt(self):
        pass

    def reset(self):
        pass

    def pause(self):
        pass

    def resume(self):
        pass

    def flatten(self, name=None):
        pass

    def set_mode(self, mode):
        return True, "ok"

    def start(self):
        pass

    def stop(self):
        pass

    def reload(self):
        self.reloaded += 1

    def rebalance_status(self):
        return {"allocations": [], "mode": "soft", "last_rebalance_at": ""}

    def run_rebalance_now(self):
        return {"ran": True}


def _client(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    app = create_app(
        controller=FakeController(),
        profiles=profiles,
        creds=None,
        token="t",
    )
    return TestClient(app, headers={"X-Token": "t"})


def test_get_rebalance_settings_defaults(tmp_path):
    client = _client(tmp_path)
    r = client.get("/api/rebalance/settings")
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert r.json()["mode"] == "hard"


def test_post_rebalance_targets_validates_sum(tmp_path):
    client = _client(tmp_path)
    r = client.post("/api/rebalance/targets", json={"targets": {"a": 0.7, "b": 0.5}})
    assert r.status_code == 400


def test_get_rebalance_status_shape(tmp_path):
    client = _client(tmp_path)
    r = client.get("/api/rebalance/status")
    assert r.status_code == 200
    body = r.json()
    assert "allocations" in body and "mode" in body and "last_rebalance_at" in body
