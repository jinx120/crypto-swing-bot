from __future__ import annotations

import json
import sqlite3

from swingbot.profile import StrategyProfile


class ProfileStore:
    """SQLite-backed strategy profiles + an 'active' pointer."""

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS profiles (name TEXT PRIMARY KEY, data TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        self._conn.commit()

    def save(self, name: str, profile: dict) -> None:
        try:
            StrategyProfile.from_dict(profile)
        except (TypeError, Exception) as exc:
            raise ValueError(f"invalid profile: {exc}") from exc
        self._conn.execute(
            "INSERT OR REPLACE INTO profiles (name, data) VALUES (?, ?)",
            (name, json.dumps(profile)),
        )
        self._conn.commit()

    def get(self, name: str) -> dict | None:
        row = self._conn.execute(
            "SELECT data FROM profiles WHERE name=?", (name,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM profiles ORDER BY name").fetchall()
        return [r[0] for r in rows]

    def delete(self, name: str) -> None:
        self._conn.execute("DELETE FROM profiles WHERE name=?", (name,))
        self._conn.commit()

    def set_active(self, name: str) -> None:
        if self.get(name) is None:
            raise ValueError(f"unknown profile {name!r}")
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('active', ?)", (name,)
        )
        self._conn.commit()

    def get_active_name(self) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key='active'").fetchone()
        return row[0] if row else None

    def get_active(self) -> dict | None:
        name = self.get_active_name()
        return self.get(name) if name else None
