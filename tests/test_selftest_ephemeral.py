import json
import os

import pytest

from swingbot.selftest.ephemeral import EphemeralApp


class FakeProc:
    def __init__(self, pid=4242, alive=True):
        self.pid = pid
        self._alive = alive
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self._alive else 1

    def terminate(self):
        self.terminated = True
        self._alive = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True
        self._alive = False


def _app(tmp_path, http_results, proc=None, **kw):
    """http_results: list of bools consumed per readiness poll."""
    calls = {"popen": [], "env": []}

    def popen_fn(cmd, env=None, **kwargs):
        calls["popen"].append(cmd)
        calls["env"].append(env)
        return proc or FakeProc()

    it = iter(http_results)

    def http_get(url, timeout=2.0):
        return next(it, False)

    app = EphemeralApp(port=8001, agent_dir=str(tmp_path / "agent"),
                       popen_fn=popen_fn, http_get=http_get,
                       startup_timeout_s=0.2, poll_interval_s=0.01, **kw)
    return app, calls


def test_start_sets_env_writes_token_and_pidfile(tmp_path):
    app, calls = _app(tmp_path, [False, True])
    app.start()
    try:
        env = calls["env"][0]
        assert env["SWINGBOT_PORT"] == "8001"
        assert env["SWINGBOT_HOST"] == "127.0.0.1"
        data_dir = env["SWINGBOT_DATA_DIR"]
        assert open(os.path.join(data_dir, "token")).read() == app.token
        pid_meta = json.load(open(os.path.join(str(tmp_path / "agent"), "ephemeral.pid")))
        assert pid_meta["pid"] == 4242 and pid_meta["port"] == 8001
        assert app.base_url == "http://127.0.0.1:8001"
    finally:
        app.stop()


def test_stop_terminates_removes_pidfile_and_data_dir(tmp_path):
    app, _ = _app(tmp_path, [True])
    app.start()
    data_dir = app.data_dir
    app.stop()
    assert not os.path.exists(os.path.join(str(tmp_path / "agent"), "ephemeral.pid"))
    assert not os.path.exists(data_dir)


def test_startup_timeout_raises_and_tears_down(tmp_path):
    proc = FakeProc()
    app, _ = _app(tmp_path, [False] * 100, proc=proc)
    with pytest.raises(RuntimeError):
        app.start()
    assert proc.terminated or proc.killed
    assert app.data_dir is None or not os.path.exists(app.data_dir)


def test_early_process_death_raises(tmp_path):
    proc = FakeProc(alive=False)
    app, _ = _app(tmp_path, [False] * 100, proc=proc)
    with pytest.raises(RuntimeError, match="exited"):
        app.start()


def test_stale_pidfile_is_killed_on_start(tmp_path):
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "ephemeral.pid").write_text(json.dumps({"pid": 99999, "port": 8001}))
    killed = []
    app, _ = _app(tmp_path, [True])
    app.kill_fn = lambda pid: killed.append(pid)
    app.start()
    try:
        assert killed == [99999]
    finally:
        app.stop()


def test_seed_proposals_writes_store_file(tmp_path):
    app, _ = _app(tmp_path, [True])
    app.start()
    try:
        app.seed_proposals([{"id": "x1", "action": "arm"}])
        rows = json.load(open(os.path.join(app.data_dir, "brain_proposals.json")))
        assert rows[0]["id"] == "x1"
    finally:
        app.stop()


def test_context_manager(tmp_path):
    app, _ = _app(tmp_path, [True])
    with app as a:
        assert a.base_url.endswith(":8001")
    assert not os.path.exists(os.path.join(str(tmp_path / "agent"), "ephemeral.pid"))
