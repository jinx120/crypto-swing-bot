import os

from fastapi.testclient import TestClient

from swingbot.selftest.agentstore import AgentRunStore
from swingbot.web import create_app


class FakeController:
    def status(self): return {"portfolio": {"mode": "paper"}, "strategies": []}
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}


def _client(tmp_path, seed_runs=True):
    agent_dir = str(tmp_path / "agent")
    store = AgentRunStore(agent_dir)
    if seed_runs:
        store.add({"ts": 1.0, "green": True, "checks": [], "route_findings": [],
                   "traces": [{"session": "s1-tabs", "ok": True, "steps": []}],
                   "drift": [], "proposal_ids": []})
        store.add({"ts": 2.0, "green": True, "checks": [], "route_findings": [],
                   "traces": [{"session": "s1-tabs", "ok": False, "steps": []}],
                   "drift": [{"session": "s1-tabs", "kind": "drift"}],
                   "proposal_ids": ["abc"]})
        os.makedirs(store.screenshot_dir, exist_ok=True)
        with open(os.path.join(store.screenshot_dir, "s1.png"), "wb") as f:
            f.write(b"\x89PNG fake")
    app = create_app(controller=FakeController(), profiles=None, creds=None,
                     token="tok", agent_dir=agent_dir)
    return TestClient(app)


def test_runs_returns_summaries_newest_last(tmp_path):
    r = _client(tmp_path).get("/api/agent/runs")
    assert r.status_code == 200
    runs = r.json()
    assert len(runs) == 2
    assert runs[-1]["drift_count"] == 1
    assert runs[-1]["sessions"] == [{"session": "s1-tabs", "ok": False}]
    assert "traces" not in runs[-1]


def test_latest_returns_full_run(tmp_path):
    r = _client(tmp_path).get("/api/agent/runs/latest")
    assert r.status_code == 200
    assert r.json()["proposal_ids"] == ["abc"]


def test_latest_empty_when_no_runs(tmp_path):
    r = _client(tmp_path, seed_runs=False).get("/api/agent/runs/latest")
    assert r.status_code == 200 and r.json() == {}


def test_artifact_served(tmp_path):
    r = _client(tmp_path).get("/api/agent/artifacts/s1.png")
    assert r.status_code == 200
    assert r.content.startswith(b"\x89PNG")


def test_artifact_traversal_rejected(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/agent/artifacts/..%2Fruns.json").status_code == 404
    assert c.get("/api/agent/artifacts/nope.png").status_code == 404


def test_endpoints_404_or_empty_without_agent_dir(tmp_path):
    app = create_app(controller=FakeController(), profiles=None, creds=None,
                     token="tok")
    c = TestClient(app)
    assert c.get("/api/agent/runs").json() == []
    assert c.get("/api/agent/runs/latest").json() == {}
    assert c.get("/api/agent/artifacts/x.png").status_code == 404
