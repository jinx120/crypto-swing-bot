from __future__ import annotations

import sqlite3
import threading


class RuntimeStateStore:
    """SQLite-backed durable lifecycle state for the trading loop.

    Phase 2 persists exactly one fact: whether the operator wants the loop
    running across restarts (`running_desired`). The default (no row) is False,
    so existing installations are never silently opted into auto-start.

    The connection is opened with ``check_same_thread=False`` because web request
    threads and the lifespan/auto-start path touch it concurrently; an ``RLock``
    serializes every access so SQLite never sees overlapping statements.
    """

    def __init__(self, db_path: str):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS runtime_state (key TEXT PRIMARY KEY, value TEXT)")

    def get_running_desired(self) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM runtime_state WHERE key='running_desired'").fetchone()
        return row is not None and row[0] == "1"

    def set_running_desired(self, desired: bool) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO runtime_state (key, value) VALUES ('running_desired', ?)",
                ("1" if desired else "0",))
