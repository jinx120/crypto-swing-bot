import json
import os

from swingbot.selftest import DriftFinding, SessionStep, SessionTrace
from swingbot.selftest.agentstore import AgentRunStore


def _run(ts=1.0, green=True):
    return {"ts": ts, "green": green, "checks": [], "route_findings": [],
            "traces": [], "drift": [], "proposal_ids": []}


def test_types_have_expected_fields():
    s = SessionStep(desc="open dashboard", action="goto", ok=True)
    t = SessionTrace(session="s1-tabs", ok=True, steps=[s])
    d = DriftFinding(session="s1-tabs", step="open dashboard", expected="renders",
                     observed="404", doc_ref="frontend/src/guide.md §x", kind="drift")
    assert s.expectation_key == "" and t.duration_s == 0.0 and d.suggestion == ""


def test_round_trip_and_latest(tmp_path):
    store = AgentRunStore(str(tmp_path / "agent"))
    assert store.all() == [] and store.latest() is None
    store.add(_run(ts=1.0))
    store.add(_run(ts=2.0, green=False))
    assert [r["ts"] for r in store.all()] == [1.0, 2.0]
    assert store.latest()["green"] is False


def test_ring_caps_at_20(tmp_path):
    store = AgentRunStore(str(tmp_path / "agent"), cap=20)
    for i in range(25):
        store.add(_run(ts=float(i)))
    runs = store.all()
    assert len(runs) == 20 and runs[0]["ts"] == 5.0 and runs[-1]["ts"] == 24.0


def test_corrupt_file_tolerated(tmp_path):
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "runs.json").write_text("{not json")
    store = AgentRunStore(str(agent_dir))
    assert store.all() == []
    store.add(_run())
    assert len(store.all()) == 1


def test_creates_dirs_and_screenshot_dir(tmp_path):
    store = AgentRunStore(str(tmp_path / "deep" / "agent"))
    store.add(_run())
    assert os.path.isfile(store.path)
    assert store.screenshot_dir.endswith(os.path.join("agent", "screenshots"))
    assert json.load(open(store.path))[0]["green"] is True
