import threading
import time

import pytest

from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
from tests.test_supervisor import FakeBroker, FakeMarket, _bars, _profile


class NoCredentials:
    def get(self):
        return None


def _supervisor(tmp_path, *, broker=None, creds=None, mode="paper"):
    profiles = ProfileStore(str(tmp_path / "profiles.db"))
    profiles.save("btc", _profile("BTC/USD"))
    profiles.arm("btc")
    market = FakeMarket({"BTC/USD": _bars()})
    return PortfolioSupervisor(
        profiles=profiles,
        creds=creds,
        state_db=str(tmp_path / "state.db"),
        market=market,
        broker=broker if broker is not None else FakeBroker(),
        mode=mode,
    )


def _install_stubborn_thread(sup):
    release = threading.Event()
    thread = threading.Thread(target=release.wait, daemon=True)
    sup._thread = thread
    sup._running = True
    thread.start()
    return thread, release


def test_reload_waits_for_inflight_tick(tmp_path):
    sup = _supervisor(tmp_path)
    sup.build()
    tick_entered = threading.Event()
    release_tick = threading.Event()
    reload_finished = threading.Event()

    strategy = sup._strategies["btc"]
    original_tick = strategy["orch"].tick

    def blocking_tick(now):
        tick_entered.set()
        assert release_tick.wait(timeout=2)
        original_tick(now)

    strategy["orch"].tick = blocking_tick
    tick_thread = threading.Thread(target=sup.tick_all)
    tick_thread.start()
    assert tick_entered.wait(timeout=2)

    reload_thread = threading.Thread(
        target=lambda: (sup.reload(), reload_finished.set()))
    reload_thread.start()
    time.sleep(0.1)
    assert not reload_finished.is_set()

    release_tick.set()
    tick_thread.join(timeout=2)
    reload_thread.join(timeout=2)
    assert not tick_thread.is_alive()
    assert not reload_thread.is_alive()
    assert reload_finished.is_set()


def test_stop_interrupts_loop_sleep_and_is_idempotent(tmp_path):
    sup = _supervisor(tmp_path)
    ticked = threading.Event()
    sup.tick_all = ticked.set
    sup._poll_seconds = lambda: 60

    sup.start()
    assert ticked.wait(timeout=2)
    started = time.monotonic()
    sup.stop()
    elapsed = time.monotonic() - started
    sup.stop()

    assert elapsed < 0.5
    assert sup._thread is None
    assert sup.lifecycle_state()["running_actual"] is False


def test_stop_retains_live_thread_after_join_timeout(tmp_path):
    sup = _supervisor(tmp_path)
    sup._join_timeout = 0.05
    thread, release = _install_stubborn_thread(sup)
    try:
        sup.stop()
        assert sup._thread is thread
        assert thread.is_alive()
        state = sup.lifecycle_state()
        assert state["running_flag"] is False
        assert state["thread_alive"] is True
        assert state["running_actual"] is False
    finally:
        release.set()
        thread.join(timeout=2)


def test_start_refuses_while_prior_thread_is_alive(tmp_path):
    sup = _supervisor(tmp_path)
    thread, release = _install_stubborn_thread(sup)
    sup._running = False
    try:
        with pytest.raises(RuntimeError, match="previous loop thread still alive"):
            sup.start()
    finally:
        release.set()
        thread.join(timeout=2)


def test_mode_does_not_change_when_stop_times_out(tmp_path):
    sup = _supervisor(tmp_path, mode="live")
    sup._join_timeout = 0.05
    thread, release = _install_stubborn_thread(sup)
    try:
        ok, reason = sup.set_mode("paper")
        assert ok is False
        assert "still alive" in reason
        assert sup.mode == "live"
    finally:
        release.set()
        thread.join(timeout=2)


def test_start_without_credentials_leaves_no_loop(tmp_path):
    sup = _supervisor(tmp_path, broker=FakeBroker())
    sup._broker = None
    sup.creds = NoCredentials()

    with pytest.raises(RuntimeError, match="credentials not set"):
        sup.start()

    state = sup.lifecycle_state()
    assert state["running_flag"] is False
    assert state["thread_alive"] is False
    assert state["running_actual"] is False


def test_lifecycle_state_reports_running_pause_and_halt(tmp_path):
    sup = _supervisor(tmp_path)
    ticked = threading.Event()
    sup.tick_all = ticked.set
    sup._poll_seconds = lambda: 60

    sup.start()
    try:
        assert ticked.wait(timeout=2)
        running = sup.lifecycle_state()
        assert running["running_flag"] is True
        assert running["thread_alive"] is True
        assert running["running_actual"] is True

        sup.pause()
        assert sup.lifecycle_state()["paused"] is True
        sup.halt()
        assert sup.lifecycle_state()["halted"] is True
    finally:
        sup.stop()
