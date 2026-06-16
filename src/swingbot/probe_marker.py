from __future__ import annotations

import sqlite3


class ProbeMarkerStore:
    """Durable marker for a completed proof-of-life probe."""

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS probe_markers (name TEXT PRIMARY KEY)")
        self._conn.commit()

    def is_complete(self, name: str) -> bool:
        return (
            self._conn.execute("SELECT 1 FROM probe_markers WHERE name=?", (name,)).fetchone()
            is not None
        )

    def mark_complete(self, name: str) -> None:
        self._conn.execute("INSERT OR IGNORE INTO probe_markers (name) VALUES (?)", (name,))
        self._conn.commit()


def probe_should_fire(
    store: ProbeMarkerStore, *, enabled: bool, mode: str, name: str = "paper_probe"
) -> bool:
    """Return True only when the opt-in paper probe has not completed."""
    if not enabled or mode != "paper":
        return False
    return not store.is_complete(name)
