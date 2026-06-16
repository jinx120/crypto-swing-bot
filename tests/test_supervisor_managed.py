from swingbot.probe_marker import ProbeMarkerStore
from swingbot.supervisor import PortfolioSupervisor
from swingbot.types import DecisionCode, DecisionResult


def _supervisor(tmp_path, **kw):
    db = str(tmp_path / "swingbot.db")
    return PortfolioSupervisor(
        profiles=__import__("swingbot.profiles", fromlist=["ProfileStore"]).ProfileStore(db),
        creds=None,
        state_db=db,
        mode="paper",
        **kw,
    )


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
