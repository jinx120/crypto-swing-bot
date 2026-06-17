from datetime import datetime, timezone
from core_engine.contracts import JournalEvent
from core_engine.journal import EngineJournal


def _ev(kind, reason, **payload):
    return JournalEvent(ts=datetime.now(timezone.utc), kind=kind,
                        symbol="BTC/USD", reason=reason, payload=payload)


def test_log_and_read_back(tmp_path):
    j = EngineJournal(str(tmp_path / "j.db"))
    j.log(_ev("decision", "hold", score=0.2))
    j.log(_ev("order", "entry", qty=0.01))
    assert len(j.events()) == 2
    assert len(j.events(kind="order")) == 1


def test_report_counts_wins_losses(tmp_path):
    j = EngineJournal(str(tmp_path / "j.db"))
    j.log(_ev("pnl", "closed win", realized=12.0, won=True))
    j.log(_ev("pnl", "closed loss", realized=-5.0, won=False))
    r = j.report()
    assert r.wins == 1 and r.losses == 1
    assert round(r.realized_pnl, 2) == 7.0
