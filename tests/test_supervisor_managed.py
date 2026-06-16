from datetime import datetime, timezone

from swingbot.managed_profiles import managed_definitions
from swingbot.probe_marker import ProbeMarkerStore
from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
from swingbot.types import DecisionCode, DecisionResult, OrderSide, PendingOrder, Regime
from tests.test_supervisor import T0, FakeBroker, FakeMarket, _bars


def _supervisor(tmp_path, **kw):
    db = str(tmp_path / "swingbot.db")
    return PortfolioSupervisor(
        profiles=__import__("swingbot.profiles", fromlist=["ProfileStore"]).ProfileStore(db),
        creds=None,
        state_db=db,
        mode="paper",
        **kw,
    )


def _probe_supervisor(tmp_path, mode="paper"):
    """A built supervisor whose only armed strategy is the managed paper probe."""
    profiles = ProfileStore(str(tmp_path / "p.db"))
    profiles.save("paper_probe", managed_definitions(enable_probe=True)["paper_probe"])
    profiles.arm("paper_probe")
    market = FakeMarket({"BTC/USD": _bars(100.0)})
    broker = FakeBroker()
    marker = ProbeMarkerStore(str(tmp_path / "probe.db"))
    sup = PortfolioSupervisor(
        profiles=profiles, creds=None, state_db=str(tmp_path / "s.db"),
        market=market, broker=broker, mode=mode, probe_marker=marker,
    )
    sup.build()
    return sup, broker, marker


def test_build_runs_reconcile_hook(tmp_path):
    calls = []
    sup = _supervisor(tmp_path, reconcile=lambda: calls.append(True))
    try:
        sup.build()
    except Exception:
        pass
    assert calls == [True]


def test_note_decision_marks_probe_complete_once(tmp_path):
    marker = ProbeMarkerStore(str(tmp_path / "probe.db"))
    sup = _supervisor(tmp_path, probe_marker=marker)
    assert marker.is_complete("paper_probe") is False
    sup.note_managed_decision("paper_probe", DecisionResult(DecisionCode.ENTERED, "entered"))
    assert marker.is_complete("paper_probe") is True


def test_note_decision_ignores_non_probe_and_non_terminal(tmp_path):
    marker = ProbeMarkerStore(str(tmp_path / "probe.db"))
    sup = _supervisor(tmp_path, probe_marker=marker)
    sup.note_managed_decision("btc_trend", DecisionResult(DecisionCode.ENTERED, "x"))
    sup.note_managed_decision("paper_probe", DecisionResult(DecisionCode.SIGNAL_BELOW_THRESHOLD, "x"))
    assert marker.is_complete("paper_probe") is False


# --- fire-once gate: the completed probe must not re-enter (regression) ---


def test_completed_probe_does_not_reenter_when_flat(tmp_path):
    sup, broker, marker = _probe_supervisor(tmp_path)
    marker.mark_complete("paper_probe")            # probe already fired earlier
    called = []
    sup._strategies["paper_probe"]["orch"].tick = lambda now: called.append(now)

    sup.tick_all(T0)

    assert called == []                            # entry pipeline never invoked
    assert broker.buys == []                       # no new order placed
    row = sup._telemetry.recent(strategy="paper_probe")[0]
    assert row.decision_code is DecisionCode.PROBE_COMPLETE
    assert row.decide == "ok"


def test_uncompleted_probe_still_runs_entry_pipeline(tmp_path):
    sup, broker, marker = _probe_supervisor(tmp_path)
    called = []

    def fake_tick(now):
        called.append(now)
        return DecisionResult(DecisionCode.ENTERED, "entered")

    sup._strategies["paper_probe"]["orch"].tick = fake_tick

    sup.tick_all(T0)

    assert called == [T0]                          # not suppressed: pipeline ran
    assert marker.is_complete("paper_probe") is True  # firing marked it complete


def test_completed_probe_still_manages_open_position(tmp_path):
    from tests.test_supervisor_telemetry import _position

    sup, broker, marker = _probe_supervisor(tmp_path)
    marker.mark_complete("paper_probe")
    # A probe that still holds a position must keep ticking so it can exit:
    # local position (drives position_exists) + broker position (reconcile confirms it).
    sup._store.save_position(_position(), strategy="paper_probe")
    broker.positions["BTC/USD"] = {
        "symbol": "BTC/USD", "qty": 1.0, "avg_entry_price": 100.0, "market_value": 100.0,
    }
    called = []

    def fake_tick(now):
        called.append(now)
        return DecisionResult(DecisionCode.MANAGED_NO_EXIT, "holding")

    sup._strategies["paper_probe"]["orch"].tick = fake_tick

    sup.tick_all(T0)

    assert called == [T0]                          # manage path is not suppressed


def test_status_labels_and_probe_complete(tmp_path):
    sup, broker, marker = _probe_supervisor(tmp_path)
    st = sup.status()
    probe = next(s for s in st["strategies"] if s["name"] == "paper_probe")
    assert probe["kind"] == "probe"
    assert probe["label"] == "proof-of-life probe"
    assert probe["probe_complete"] is False

    marker.mark_complete("paper_probe")

    probe2 = next(s for s in sup.status()["strategies"] if s["name"] == "paper_probe")
    assert probe2["probe_complete"] is True


def test_status_includes_pending_orders(tmp_path):
    sup, broker, marker = _probe_supervisor(tmp_path)
    order = PendingOrder(
        client_order_id="cid-1",
        broker_order_id=None,
        symbol="BTC/USD",
        side=OrderSide.BUY,
        submitted_at=datetime(2026, 6, 16, tzinfo=timezone.utc),
        requested_qty=0.01,
        stop=None,
        tp=None,
        max_hold_until=datetime(2026, 6, 17, tzinfo=timezone.utc),
        score_at_entry=0.9,
        regime_at_entry=Regime.UPTREND,
        exit_reason=None,
        observed_exit_price=None,
    )
    sup._store.save_pending_order(order, strategy="paper_probe")

    pend = sup.status()["pending_orders"]

    assert len(pend) == 1
    assert pend[0]["strategy"] == "paper_probe"
    assert pend[0]["symbol"] == "BTC/USD"
    assert pend[0]["side"] == "buy"
    assert pend[0]["client_order_id"] == "cid-1"


def test_status_open_position_has_unrealized_pnl(tmp_path):
    """An open position is annotated from the latest local market bar."""
    sup, broker, marker = _probe_supervisor(tmp_path)
    name = "paper_probe"
    strat = sup._strategies[name]

    class _Pos:
        symbol = "BTC/USD"
        entry_price = 100.0
        qty = 2.0
        stop = 90.0
        tp = 120.0
        max_hold_until = datetime(2026, 6, 17, tzinfo=timezone.utc)
        entry_ts = datetime(2026, 6, 16, tzinfo=timezone.utc)

    strat["view"].load_position = lambda: _Pos()

    st = sup.status()
    s = next(x for x in st["strategies"] if x["name"] == name)

    assert s["position"] is not None
    mark_price = s["position"]["mark_price"]
    assert mark_price is not None
    assert s["position"]["mark_ts"] is not None
    assert abs(s["position"]["unrealized"] - (mark_price - 100.0) * 2.0) < 1e-9


def test_status_unrealized_null_without_market(tmp_path):
    sup, broker, marker = _probe_supervisor(tmp_path)
    name = "paper_probe"
    strat = sup._strategies[name]
    sup.market = None

    class _Pos:
        symbol = "BTC/USD"
        entry_price = 100.0
        qty = 2.0
        stop = 90.0
        tp = 120.0
        max_hold_until = datetime(2026, 6, 17, tzinfo=timezone.utc)
        entry_ts = datetime(2026, 6, 16, tzinfo=timezone.utc)

    strat["view"].load_position = lambda: _Pos()

    s = next(x for x in sup.status()["strategies"] if x["name"] == name)

    assert s["position"]["mark_price"] is None
    assert s["position"]["mark_ts"] is None
    assert s["position"]["unrealized"] is None
