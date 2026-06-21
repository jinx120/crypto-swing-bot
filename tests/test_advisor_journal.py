from swingbot.advisor.journal import TuningJournal


def test_record_and_list(tmp_path):
    journal = TuningJournal(str(tmp_path / "tuning.db"))
    batch_id = journal.record(
        [
            {
                "symbol": "BTC/USD",
                "param": "tp_pct",
                "before": 0.015,
                "after": 0.02,
                "rationale": "winners run",
            }
        ]
    )
    rows = journal.list_entries()
    assert len(rows) == 1
    assert rows[0]["batch_id"] == batch_id
    assert rows[0]["after"] == 0.02


def test_revert_returns_inverse(tmp_path):
    journal = TuningJournal(str(tmp_path / "tuning.db"))
    batch_id = journal.record(
        [
            {
                "symbol": "BTC/USD",
                "param": "tp_pct",
                "before": 0.015,
                "after": 0.02,
                "rationale": "x",
            }
        ]
    )
    inverse = journal.revert(batch_id)
    assert inverse == [{"symbol": "BTC/USD", "param": "tp_pct", "value": 0.015}]
    assert journal.list_entries()[0]["reverted"] is True
