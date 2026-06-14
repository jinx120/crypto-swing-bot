import threading
import time

import pytest

from swingbot.profiles import ProfileStore
from swingbot.runtime_state import RuntimeStateStore
from swingbot.supervisor import PortfolioSupervisor
from tests.test_supervisor import FakeBroker, FakeMarket, _bars, _profile


def _supervisor(tmp_path, *, broker=None, creds=None, mode="paper",
                runtime_state=None, armed=True):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    if armed:
        profiles.save("btc", _profile("BTC/USD"))
        profiles.arm("btc")
    market = FakeMarket({"BTC/USD": _bars()})
    return PortfolioSupervisor(
        profiles=profiles, creds=creds,
        state_db=str(tmp_path / "s.db"), market=market,
        broker=broker if broker is not None else FakeBroker(),
        mode=mode, runtime_state=runtime_state)


def test_running_desired_reflects_store(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    sup = _supervisor(tmp_path, runtime_state=rs)
    assert sup.running_desired is False
    rs.set_running_desired(True)
    assert sup.running_desired is True


def test_running_desired_false_without_store(tmp_path):
    sup = _supervisor(tmp_path, runtime_state=None)
    assert sup.running_desired is False
    sup.mark_desired(True)  # no store: must be a harmless no-op, not a crash
    assert sup.running_desired is False


def test_mark_desired_persists_through_store(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    sup = _supervisor(tmp_path, runtime_state=rs)
    sup.mark_desired(True)
    assert rs.get_running_desired() is True
    sup.mark_desired(False)
    assert rs.get_running_desired() is False


def test_lifecycle_state_includes_desire_and_startup_error(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    rs.set_running_desired(True)
    sup = _supervisor(tmp_path, runtime_state=rs)
    state = sup.lifecycle_state()
    assert state["running_desired"] is True
    assert state["startup_error"] is None


def test_auto_start_resumes_desired_paper_armed_loop(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    rs.set_running_desired(True)
    sup = _supervisor(tmp_path, runtime_state=rs)
    sup._poll_seconds = lambda: 60   # keep the loop asleep after one tick
    try:
        sup.auto_start_if_desired()
        assert sup.lifecycle_state()["running_actual"] is True
        assert sup.startup_error is None
    finally:
        sup.stop()


def test_auto_start_noop_when_not_desired(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))  # default desired=False
    sup = _supervisor(tmp_path, runtime_state=rs)
    sup.auto_start_if_desired()
    assert sup.lifecycle_state()["running_actual"] is False
    assert sup.startup_error is None


def test_auto_start_skips_live_mode(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    rs.set_running_desired(True)
    sup = _supervisor(tmp_path, mode="live", runtime_state=rs)
    sup.auto_start_if_desired()
    assert sup.lifecycle_state()["running_actual"] is False


def test_auto_start_reports_no_armed_strategies(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    rs.set_running_desired(True)
    sup = _supervisor(tmp_path, runtime_state=rs, armed=False)
    sup.auto_start_if_desired()
    assert sup.lifecycle_state()["running_actual"] is False
    assert "no armed strategies" in sup.startup_error


def test_auto_start_captures_start_failure_without_raising(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    rs.set_running_desired(True)
    # No broker and no creds -> build() raises "Alpaca credentials not set".
    sup = _supervisor(tmp_path, broker=None, creds=None, runtime_state=rs)
    sup._broker = None
    sup.auto_start_if_desired()   # must not raise
    assert sup.lifecycle_state()["running_actual"] is False
    assert "credentials" in sup.startup_error


def test_auto_start_captures_runtime_state_read_failure(tmp_path):
    class FailingRuntimeState:
        def get_running_desired(self):
            raise RuntimeError("runtime-state read failed")

    sup = _supervisor(tmp_path, runtime_state=FailingRuntimeState())
    sup.auto_start_if_desired()   # must not raise
    assert "runtime-state read failed" in sup.startup_error


class RecordingRuntimeState:
    def __init__(self, calls, desired=False):
        self.calls = calls
        self.desired = desired

    def get_running_desired(self):
        return self.desired

    def set_running_desired(self, desired):
        self.calls.append(("mark_desired", desired))
        self.desired = desired


def test_request_start_marks_desire_after_success(tmp_path):
    calls = []
    rs = RecordingRuntimeState(calls)
    sup = _supervisor(tmp_path, runtime_state=rs)
    sup.startup_error = "old auto-start failure"
    sup.start = lambda: calls.append("start")

    sup.request_start()

    assert calls == ["start", ("mark_desired", True)]
    assert sup.startup_error is None


def test_request_start_failure_does_not_mark_desire(tmp_path):
    calls = []
    rs = RecordingRuntimeState(calls)
    sup = _supervisor(tmp_path, runtime_state=rs)
    sup.start = lambda: (_ for _ in ()).throw(RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        sup.request_start()

    assert calls == []


class _RaiseOnSetRuntimeState:
    """Runtime store whose desire-read works but desire-write raises."""
    def __init__(self):
        self._desired = False

    def get_running_desired(self):
        return self._desired

    def set_running_desired(self, desired):
        raise RuntimeError("disk full")


def test_request_start_rolls_back_when_persist_fails(tmp_path):
    from swingbot.supervisor import DesirePersistError
    sup = _supervisor(tmp_path, runtime_state=_RaiseOnSetRuntimeState())
    with pytest.raises(DesirePersistError) as exc:
        sup.request_start()
    state = sup.lifecycle_state()
    assert state["running_actual"] is False
    assert state["thread_alive"] is False
    assert exc.value.rolled_back is True
    assert exc.value.persist_error is not None


def test_request_start_does_not_clear_startup_error_on_persist_failure(tmp_path):
    sup = _supervisor(tmp_path, runtime_state=_RaiseOnSetRuntimeState())
    sup.startup_error = "auto-start failed: earlier boom"
    with pytest.raises(Exception):
        sup.request_start()
    assert sup.startup_error == "auto-start failed: earlier boom"


def test_request_stop_clears_desire_before_stop(tmp_path):
    calls = []
    rs = RecordingRuntimeState(calls, desired=True)
    sup = _supervisor(tmp_path, runtime_state=rs)
    sup.stop = lambda: calls.append("stop")

    sup.request_stop()

    assert calls == [("mark_desired", False), "stop"]


def test_concurrent_stop_cannot_be_overwritten_by_inflight_start(tmp_path):
    calls = []
    rs = RecordingRuntimeState(calls)
    sup = _supervisor(tmp_path, runtime_state=rs)
    start_entered = threading.Event()
    release_start = threading.Event()

    def blocking_start():
        calls.append("start")
        start_entered.set()
        assert release_start.wait(timeout=2)

    sup.start = blocking_start
    sup.stop = lambda: calls.append("stop")
    start_thread = threading.Thread(target=sup.request_start)
    stop_thread = threading.Thread(target=sup.request_stop)

    start_thread.start()
    assert start_entered.wait(timeout=2)
    stop_thread.start()
    time.sleep(0.05)
    assert "stop" not in calls

    release_start.set()
    start_thread.join(timeout=2)
    stop_thread.join(timeout=2)

    assert not start_thread.is_alive()
    assert not stop_thread.is_alive()
    assert calls == ["start", ("mark_desired", True), ("mark_desired", False), "stop"]
    assert rs.desired is False
