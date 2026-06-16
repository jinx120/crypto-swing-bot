"""Phase 6 deterministic acceptance harness.

Mirrors the live webmain wiring (managed reconcile + probe marker + persisted
desire + auto_start_if_desired) with a fake broker/market, and composes the
spec Phase 6 runbook outcomes into one place. The AUTHORITATIVE acceptance is
the live paper run recorded in docs/PHASE6_LIVE_ACCEPTANCE.md; this suite is the
reproducible, Alpaca-free support for it.
"""

from datetime import timedelta

from swingbot.managed_profiles import reconcile_managed_profiles
from swingbot.probe_marker import ProbeMarkerStore
from swingbot.profiles import ProfileStore
from swingbot.runtime_state import RuntimeStateStore
from swingbot.supervisor import PortfolioSupervisor
from swingbot.types import (
    BrokerOrder,
    DecisionCode,
    DecisionResult,
    OrderSide,
    OrderStatus,
    PendingOrder,
    Regime,
)
from tests.test_supervisor import FakeBroker, FakeMarket, T0, _bars
from tests.test_supervisor_telemetry import _position


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


def test_probe_entry_confirmed_promotes_position_marks_complete_and_records_cycle(
    tmp_path,
):
    broker = FakeBroker()
    sup, broker, marker, profiles = _wire(
        tmp_path, enable_probe=True, broker=broker
    )
    assert "paper_probe" in set(profiles.list_armed())

    # A probe entry was submitted last cycle: a pending buy is on the books.
    pending = PendingOrder(
        client_order_id="probe-coid",
        broker_order_id="probe-coid",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        submitted_at=T0,
        requested_qty=1.0,
        stop=None,
        tp=None,
        max_hold_until=T0 + timedelta(hours=8),
        score_at_entry=1.0,
        regime_at_entry=Regime.UPTREND,
        exit_reason=None,
        observed_exit_price=None,
    )
    sup._store.save_pending_order(pending, strategy="paper_probe")

    # Broker confirms the fill and reports the resulting position (broker truth).
    broker.order = BrokerOrder(
        "probe-1",
        "BTC/USD",
        OrderSide.BUY,
        OrderStatus.FILLED,
        1.0,
        1.0,
        100.0,
        "probe-coid",
    )
    broker.positions["BTC/USD"] = {
        "symbol": "BTC/USD",
        "qty": 1.0,
        "avg_entry_price": 100.0,
        "market_value": 100.0,
    }

    sup.tick_all(T0)

    # Broker-confirmed position is now durable and visible.
    st = sup.status()
    probe_row = next(s for s in st["strategies"] if s["name"] == "paper_probe")
    assert probe_row["position"] is not None
    assert probe_row["position"]["qty"] == 1.0

    # The probe is durably marked complete (fire-once promise).
    sup.note_managed_decision(
        "paper_probe", DecisionResult(DecisionCode.ENTERED, "probe filled")
    )
    assert marker.is_complete("paper_probe") is True

    # A cycle record exists with a bar timestamp and a stable terminal decision code.
    row = sup._telemetry.recent(strategy="paper_probe")[0]
    assert row.bar_ts is not None
    assert isinstance(row.decision_code, DecisionCode)


def test_restart_does_not_reenter_completed_flat_probe(tmp_path):
    # Boot 1: probe enabled, marked complete, and flat (no position).
    sup, broker, marker, _profiles = _wire(tmp_path, enable_probe=True)
    marker.mark_complete("paper_probe")

    # Boot 2: container restart with fresh supervisor over the same on-disk state.
    sup2 = PortfolioSupervisor(
        profiles=sup.profiles,
        creds=None,
        state_db=str(tmp_path / "swingbot.db"),
        market=sup.market,
        broker=broker,
        mode="paper",
        probe_marker=ProbeMarkerStore(str(tmp_path / "probe_markers.db")),
    )
    sup2.build()
    before = list(broker.buys)

    sup2.tick_all(T0)

    assert broker.buys == before
    row = sup2._telemetry.recent(strategy="paper_probe")[0]
    assert row.decision_code is DecisionCode.PROBE_COMPLETE


class FailingBroker(FakeBroker):
    """A broker whose queries raise — simulates expired creds / network loss."""

    def get_account(self):
        raise ConnectionError("alpaca unreachable")

    def get_position(self, s):
        raise ConnectionError("alpaca unreachable")

    def get_order(self, order_id=None, client_order_id=None):
        raise ConnectionError("alpaca unreachable")


def test_broker_failure_does_not_false_flat_or_duplicate(tmp_path):
    broker = FailingBroker()
    sup, broker, _marker, _profiles = _wire(
        tmp_path, enable_probe=False, broker=broker
    )

    # A broker-confirmed position is already on the books for a managed strategy.
    sup._store.save_position(_position(), strategy="btc_trend")
    before_buys = list(broker.buys)

    # A cycle under total broker failure must not raise out of tick_all...
    sup.tick_all(T0)

    # ...the position is NOT cleared by an error being mistaken for "flat"...
    assert sup._store.load_position("btc_trend") is not None
    # ...and no order was placed off the back of a failed reconcile.
    assert broker.buys == before_buys

    # readiness()/trading_health() are local-only and stay answerable (never raise).
    ready = sup.readiness()
    assert isinstance(ready["ready"], bool)
    health = sup.trading_health()
    assert health["status"] in {"active", "inactive", "unhealthy"}
