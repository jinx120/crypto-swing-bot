from datetime import datetime, timedelta, timezone

from swingbot.telemetry import CycleRecord, TelemetryStore, sanitize_text
from swingbot.types import DecisionCode


T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _record(
    cycle_id: str,
    strategy: str = "btc",
    *,
    offset: int = 0,
    ingest: str = "ok",
    reconcile: str = "ok",
    manage: str = "skipped",
    decide: str = "ok",
    persist: str = "ok",
) -> CycleRecord:
    started = T0 + timedelta(seconds=offset)
    return CycleRecord(
        cycle_id=cycle_id,
        strategy=strategy,
        started_at=started,
        completed_at=started + timedelta(seconds=1),
        bar_ts=started,
        ingest=ingest,
        reconcile=reconcile,
        manage=manage,
        decide=decide,
        persist=persist,
        decision_code=DecisionCode.SIGNAL_BELOW_THRESHOLD,
        decision_reason="score below threshold",
        decision_details={"score": 0.2},
    )


def test_cycle_roundtrip_preserves_stage_outcomes_and_decision(tmp_path):
    store = TelemetryStore(str(tmp_path / "state.db"))
    expected = _record("c1", manage="ok", decide="skipped")

    store.record(expected)

    assert store.recent(limit=200, strategy="btc") == [expected]


def test_cycle_store_survives_reopen(tmp_path):
    path = str(tmp_path / "state.db")
    store = TelemetryStore(path)
    store.record(_record("c1"))
    store.close()

    assert TelemetryStore(path).recent(limit=200, strategy="btc")[0].cycle_id == "c1"


def test_retention_keeps_latest_200_per_strategy(tmp_path):
    store = TelemetryStore(str(tmp_path / "state.db"), retention=200)
    for i in range(205):
        store.record(_record(str(i), "btc", offset=i))
        store.record(_record(str(i), "eth", offset=i))

    for strategy in ("btc", "eth"):
        rows = store.recent(limit=300, strategy=strategy)
        assert [row.cycle_id for row in rows] == [str(i) for i in range(204, 4, -1)]


def test_reliability_excludes_skipped_and_reports_counts_and_window(tmp_path):
    store = TelemetryStore(str(tmp_path / "state.db"))
    store.record(_record("c1", offset=1, manage="ok", decide="skipped"))
    store.record(_record("c2", offset=2, manage="skipped", decide="failed"))

    report = store.reliability(limit=200)

    assert report["stages"]["manage"] == {
        "ok": 1, "failed": 0, "skipped": 1, "samples": 1, "ratio": 1.0,
    }
    assert report["stages"]["decide"] == {
        "ok": 0, "failed": 1, "skipped": 1, "samples": 1, "ratio": 0.0,
    }
    assert report["window_started_at"] == (T0 + timedelta(seconds=1)).isoformat()
    assert report["window_completed_at"] == (T0 + timedelta(seconds=3)).isoformat()


def test_cycle_completion_uses_only_required_manage_or_decide_stage(tmp_path):
    store = TelemetryStore(str(tmp_path / "state.db"))
    store.record(_record("c1", offset=1, manage="ok", decide="skipped"))
    store.record(_record("c2", offset=2, manage="skipped", decide="failed"))

    report = store.reliability(limit=200)

    assert report["successful_cycles"] == 1
    assert report["completed_cycles"] == 2
    assert report["cycle_completion_ratio"] == 0.5


def test_critical_floor_is_minimum_of_ingest_reconcile_persist(tmp_path):
    store = TelemetryStore(str(tmp_path / "state.db"))
    for i in range(4):
        store.record(_record(
            str(i),
            offset=i,
            ingest="ok",
            reconcile="failed" if i >= 2 else "ok",
            persist="failed" if i == 3 else "ok",
        ))

    report = store.reliability(limit=200)

    assert report["stages"]["ingest"]["ratio"] == 1.0
    assert report["stages"]["reconcile"]["ratio"] == 0.5
    assert report["stages"]["persist"]["ratio"] == 0.75
    assert report["critical_stage_floor"] == 0.5


def test_empty_reliability_has_counts_and_no_invented_ratios(tmp_path):
    report = TelemetryStore(str(tmp_path / "state.db")).reliability(limit=200)

    assert report["completed_cycles"] == 0
    assert report["successful_cycles"] == 0
    assert report["cycle_completion_ratio"] is None
    assert report["critical_stage_floor"] is None
    assert report["window_started_at"] is None
    assert report["window_completed_at"] is None
    assert all(stage["ratio"] is None for stage in report["stages"].values())


def test_sanitize_text_removes_control_chars_and_caps_at_500():
    result = sanitize_text("bad\nreason\0" + ("x" * 600))

    assert "\n" not in result
    assert "\0" not in result
    assert len(result) == 500


def test_record_and_read_rebalance_event(tmp_path):
    store = TelemetryStore(str(tmp_path / "state.db"))
    store.record_rebalance(
        ts="2026-06-19T12:00:00+00:00",
        mode="hard",
        ran=True,
        skipped_reason="",
        allocations_json="[]",
        trims_json="[]",
    )
    rows = store.recent_rebalance(limit=10)
    assert len(rows) == 1
    assert rows[0]["mode"] == "hard" and rows[0]["ran"] is True
