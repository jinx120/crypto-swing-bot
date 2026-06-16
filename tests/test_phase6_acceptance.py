"""Phase 6 deterministic acceptance harness.

Mirrors the live webmain wiring (managed reconcile + probe marker + persisted
desire + auto_start_if_desired) with a fake broker/market, and composes the
spec Phase 6 runbook outcomes into one place. The AUTHORITATIVE acceptance is
the live paper run recorded in docs/PHASE6_LIVE_ACCEPTANCE.md; this suite is the
reproducible, Alpaca-free support for it.
"""

from swingbot.managed_profiles import reconcile_managed_profiles
from swingbot.probe_marker import ProbeMarkerStore
from swingbot.profiles import ProfileStore
from swingbot.runtime_state import RuntimeStateStore
from swingbot.supervisor import PortfolioSupervisor
from tests.test_supervisor import FakeBroker, FakeMarket, _bars


def _wire(tmp_path, *, enable_probe, broker=None, desired=False):
    """Build a supervisor exactly the way webmain.py does, over a shared data dir."""
    db = str(tmp_path / "swingbot.db")
    profiles = ProfileStore(db)
    market = FakeMarket({"BTC/USD": _bars(100.0), "ETH/USD": _bars(100.0)})
    broker = broker if broker is not None else FakeBroker()
    marker = ProbeMarkerStore(str(tmp_path / "probe_markers.db"))
    runtime_state = RuntimeStateStore(db)
    if desired:
        runtime_state.set_running_desired(True)

    def _reconcile():
        reconcile_managed_profiles(
            profiles,
            enable_probe=enable_probe,
            mode="paper",
            backup_dir=str(tmp_path / "backups"),
        )

    sup = PortfolioSupervisor(
        profiles=profiles,
        creds=None,
        state_db=db,
        market=market,
        broker=broker,
        mode="paper",
        runtime_state=runtime_state,
        reconcile=_reconcile,
        probe_marker=marker,
    )
    sup.build()
    return sup, broker, marker, profiles


def test_managed_canvas_seeds_and_auto_resumes_without_start(tmp_path):
    # First boot: operator pressed Start once, desire persisted.
    _sup, _broker, _marker, profiles = _wire(
        tmp_path, enable_probe=False, desired=True
    )
    armed = set(profiles.list_armed())
    assert {"btc_trend", "eth_trend"} <= armed
    assert "paper_probe" not in armed

    # Container restart: a brand-new supervisor over the same data dir, no Start press.
    sup2, _broker2, _marker2, _profiles2 = _wire(
        tmp_path, enable_probe=False, desired=True
    )
    sup2.auto_start_if_desired()
    life = sup2.lifecycle_state()
    assert life["running_desired"] is True
    assert life["running_actual"] is True
    assert life["startup_error"] is None
    sup2.request_stop()
