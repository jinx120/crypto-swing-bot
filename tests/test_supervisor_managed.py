from swingbot.managed_profiles import managed_definitions
from swingbot.probe_marker import ProbeMarkerStore
from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
from swingbot.types import DecisionCode, DecisionResult
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
