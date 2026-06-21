from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from uuid import uuid4


class TuningJournal:
    """SQLite-backed record of advisor configuration changes."""

    def __init__(self, db_path: str):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS tuning_journal ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "batch_id TEXT NOT NULL, "
                "symbol TEXT NOT NULL, "
                "param TEXT NOT NULL, "
                "before REAL NOT NULL, "
                "after REAL NOT NULL, "
                "rationale TEXT NOT NULL, "
                "ts TEXT NOT NULL, "
                "reverted INTEGER NOT NULL DEFAULT 0)"
            )

    def record(self, entries: list[dict]) -> str:
        batch_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            for entry in entries:
                self._conn.execute(
                    "INSERT INTO tuning_journal "
                    "(batch_id, symbol, param, before, after, rationale, ts, reverted) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                    (
                        batch_id,
                        str(entry["symbol"]),
                        str(entry["param"]),
                        float(entry["before"]),
                        float(entry["after"]),
                        str(entry.get("rationale", "")),
                        str(entry.get("ts") or now),
                    ),
                )
        return batch_id

    def list_entries(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT batch_id, symbol, param, before, after, rationale, ts, reverted "
                "FROM tuning_journal ORDER BY id"
            ).fetchall()
        return [self._row_dict(row) for row in rows]

    def revert(self, batch_id: str) -> list[dict]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT symbol, param, before FROM tuning_journal "
                "WHERE batch_id=? AND reverted=0 ORDER BY id",
                (batch_id,),
            ).fetchall()
            self._conn.execute(
                "UPDATE tuning_journal SET reverted=1 WHERE batch_id=? AND reverted=0",
                (batch_id,),
            )
        return [
            {"symbol": symbol, "param": param, "value": before}
            for symbol, param, before in rows
        ]

    def revert_all(self) -> list[dict]:
        with self._lock, self._conn:
            rows = self._conn.execute(
                "SELECT symbol, param, before FROM tuning_journal "
                "WHERE reverted=0 ORDER BY id"
            ).fetchall()
            self._conn.execute("UPDATE tuning_journal SET reverted=1 WHERE reverted=0")
        return [
            {"symbol": symbol, "param": param, "value": before}
            for symbol, param, before in rows
        ]

    @staticmethod
    def _row_dict(row) -> dict:
        batch_id, symbol, param, before, after, rationale, ts, reverted = row
        return {
            "batch_id": batch_id,
            "symbol": symbol,
            "param": param,
            "before": before,
            "after": after,
            "rationale": rationale,
            "ts": ts,
            "reverted": bool(reverted),
        }
