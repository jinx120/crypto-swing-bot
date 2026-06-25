from __future__ import annotations

import json
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from swingbot.types import DecisionCode

StageOutcome = Literal["ok", "failed", "skipped"]
_STAGES = ("ingest", "reconcile", "manage", "decide", "persist")
_CRITICAL_STAGES = ("ingest", "reconcile", "persist")


@dataclass(frozen=True)
class CycleRecord:
    cycle_id: str
    strategy: str
    started_at: datetime
    completed_at: datetime
    bar_ts: datetime | None
    ingest: StageOutcome
    reconcile: StageOutcome
    manage: StageOutcome
    decide: StageOutcome
    persist: StageOutcome
    decision_code: DecisionCode
    decision_reason: str
    decision_details: dict


def sanitize_text(value: str) -> str:
    """Remove control characters and cap persisted text at 500 characters."""
    cleaned = "".join(
        " " if unicodedata.category(char).startswith("C") else char
        for char in str(value)
    )
    return cleaned[:500]


def _sanitize_json(value):
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return {str(key): _sanitize_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_json(item) for item in value]
    return value


class TelemetryStore:
    """Lock-protected SQLite store for terminal strategy-cycle records."""

    def __init__(self, db_path: str, retention: int = 200):
        self.retention = retention
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cycle_records (
                    cycle_id TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    bar_ts TEXT,
                    ingest TEXT NOT NULL,
                    reconcile TEXT NOT NULL,
                    manage TEXT NOT NULL,
                    decide TEXT NOT NULL,
                    persist TEXT NOT NULL,
                    decision_code TEXT NOT NULL,
                    decision_reason TEXT NOT NULL,
                    decision_details TEXT NOT NULL,
                    PRIMARY KEY (strategy, cycle_id)
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_cycle_records_strategy_completed
                ON cycle_records(strategy, completed_at DESC, cycle_id DESC)
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rebalance_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT,
                    mode TEXT,
                    ran INTEGER,
                    skipped_reason TEXT,
                    allocations TEXT,
                    trims TEXT
                )
                """
            )

    def record(self, record: CycleRecord) -> None:
        details = json.dumps(_sanitize_json(record.decision_details), sort_keys=True)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO cycle_records (
                    cycle_id, strategy, started_at, completed_at, bar_ts,
                    ingest, reconcile, manage, decide, persist,
                    decision_code, decision_reason, decision_details
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.cycle_id,
                    record.strategy,
                    record.started_at.isoformat(),
                    record.completed_at.isoformat(),
                    record.bar_ts.isoformat() if record.bar_ts else None,
                    record.ingest,
                    record.reconcile,
                    record.manage,
                    record.decide,
                    record.persist,
                    record.decision_code.value,
                    sanitize_text(record.decision_reason),
                    details,
                ),
            )
            self._conn.execute(
                """
                DELETE FROM cycle_records
                WHERE strategy = ?
                  AND cycle_id NOT IN (
                    SELECT cycle_id FROM cycle_records
                    WHERE strategy = ?
                    ORDER BY completed_at DESC, cycle_id DESC
                    LIMIT ?
                  )
                """,
                (record.strategy, record.strategy, self.retention),
            )

    def record_rebalance(
        self,
        *,
        ts,
        mode,
        ran,
        skipped_reason,
        allocations_json,
        trims_json,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO rebalance_events (
                    ts, mode, ran, skipped_reason, allocations, trims
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    mode,
                    1 if ran else 0,
                    skipped_reason,
                    allocations_json,
                    trims_json,
                ),
            )
            self._conn.execute(
                """
                DELETE FROM rebalance_events
                WHERE id NOT IN (
                    SELECT id FROM rebalance_events
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (self.retention,),
            )

    def recent_rebalance(self, limit: int = 50) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT ts, mode, ran, skipped_reason, allocations, trims
                FROM rebalance_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "ts": row[0],
                "mode": row[1],
                "ran": bool(row[2]),
                "skipped_reason": row[3],
                "allocations": row[4],
                "trims": row[5],
            }
            for row in rows
        ]

    def recent(self, limit: int = 200, strategy: str | None = None) -> list[CycleRecord]:
        query = "SELECT * FROM cycle_records"
        params: list = []
        if strategy is not None:
            query += " WHERE strategy = ?"
            params.append(strategy)
        query += " ORDER BY completed_at DESC, cycle_id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def recent_decisions(
        self, limit: int = 50, strategy: str | None = None
    ) -> list[CycleRecord]:
        """Recent cycles where an actual decision was made (excludes IDLE ticks).

        This is the per-bar play-by-play: entries, exits, blocks, and
        below-threshold holds — without the between-bar idle polling noise.
        """
        query = "SELECT * FROM cycle_records WHERE decision_code != 'IDLE'"
        params: list = []
        if strategy is not None:
            query += " AND strategy = ?"
            params.append(strategy)
        query += " ORDER BY completed_at DESC, cycle_id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def reliability(self, limit: int = 200, strategy: str | None = None) -> dict:
        rows = self.recent(limit=limit, strategy=strategy)
        stages = {}
        for stage in _STAGES:
            outcomes = [getattr(row, stage) for row in rows]
            ok = outcomes.count("ok")
            failed = outcomes.count("failed")
            skipped = outcomes.count("skipped")
            samples = ok + failed
            stages[stage] = {
                "ok": ok,
                "failed": failed,
                "skipped": skipped,
                "samples": samples,
                "ratio": (ok / samples) if samples else None,
            }

        successful = sum(_cycle_successful(row) for row in rows)
        completed = len(rows)
        critical_ratios = [stages[stage]["ratio"] for stage in _CRITICAL_STAGES]
        return {
            "stages": stages,
            "completed_cycles": completed,
            "successful_cycles": successful,
            "cycle_completion_ratio": (successful / completed) if completed else None,
            "critical_stage_floor": (
                min(critical_ratios) if all(ratio is not None for ratio in critical_ratios)
                else None
            ),
            "window_started_at": min(
                (row.started_at for row in rows), default=None
            ).isoformat() if rows else None,
            "window_completed_at": max(
                (row.completed_at for row in rows), default=None
            ).isoformat() if rows else None,
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _from_row(row) -> CycleRecord:
        return CycleRecord(
            cycle_id=row[0],
            strategy=row[1],
            started_at=datetime.fromisoformat(row[2]),
            completed_at=datetime.fromisoformat(row[3]),
            bar_ts=datetime.fromisoformat(row[4]) if row[4] else None,
            ingest=row[5],
            reconcile=row[6],
            manage=row[7],
            decide=row[8],
            persist=row[9],
            decision_code=DecisionCode(row[10]),
            decision_reason=row[11],
            decision_details=json.loads(row[12]),
        )


def _cycle_successful(record: CycleRecord) -> bool:
    critical_ok = all(getattr(record, stage) == "ok" for stage in _CRITICAL_STAGES)
    required_path_ok = (record.manage, record.decide) in {
        ("ok", "skipped"),
        ("skipped", "ok"),
    }
    return critical_ok and required_path_ok
