from __future__ import annotations

import json
import sqlite3

from core_engine.contracts import EnginePosition


class PositionStore:
    """Write-through persistence of the engine's open position into the
    runtime_state(key, value) table, under key 'open_position'."""

    KEY = "open_position"

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS runtime_state "
            "(key TEXT PRIMARY KEY, value TEXT)"
        )
        self._conn.commit()

    def set(self, position: EnginePosition) -> None:
        payload = {
            "symbol": position.symbol,
            "entry_price": float(position.entry_price),
            "qty": float(position.qty),
            "stop": float(position.stop) if position.stop is not None else None,
            "tp": float(position.tp) if position.tp is not None else None,
            "entry_ts": position.entry_ts.isoformat() if position.entry_ts else None,
        }
        self._conn.execute(
            "INSERT INTO runtime_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (self.KEY, json.dumps(payload)),
        )
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM runtime_state WHERE key=?", (self.KEY,))
        self._conn.commit()

    def get(self) -> dict | None:
        row = self._conn.execute(
            "SELECT value FROM runtime_state WHERE key=?", (self.KEY,)
        ).fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except (ValueError, TypeError):
            return None
