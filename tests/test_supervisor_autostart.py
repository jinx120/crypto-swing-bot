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
