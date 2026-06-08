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
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS armed "
            "(name TEXT PRIMARY KEY, live_eligible INTEGER DEFAULT 0)")
        self._conn.commit()
        self._migrate_active_to_armed()

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
        self._conn.execute("DELETE FROM armed WHERE name=?", (name,))
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

    # --- armed set + per-strategy live-eligible flag ---
    def arm(self, name: str) -> None:
        if self.get(name) is None:
            raise ValueError(f"unknown profile {name!r}")
        self._conn.execute(
            "INSERT OR IGNORE INTO armed (name, live_eligible) VALUES (?, 0)", (name,))
        self._conn.commit()

    def disarm(self, name: str) -> None:
        self._conn.execute("DELETE FROM armed WHERE name=?", (name,))
        self._conn.commit()

    def list_armed(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM armed ORDER BY name").fetchall()
        return [r[0] for r in rows]

    def is_armed(self, name: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM armed WHERE name=?", (name,)).fetchone() is not None

    def set_live_eligible(self, name: str, eligible: bool) -> None:
        if not self.is_armed(name):
            raise ValueError(f"profile {name!r} is not armed")
        self._conn.execute(
            "UPDATE armed SET live_eligible=? WHERE name=?", (1 if eligible else 0, name))
        self._conn.commit()

    def is_live_eligible(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT live_eligible FROM armed WHERE name=?", (name,)).fetchone()
        return bool(row[0]) if row else False

    def armed_with_flags(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT name, live_eligible FROM armed ORDER BY name").fetchall()
        return [{"name": n, "live_eligible": bool(le)} for n, le in rows]

    def _migrate_active_to_armed(self) -> None:
        if self.list_armed():
            return
        active = self.get_active_name()
        if active and self.get(active) is not None:
            self.arm(active)

    # --- portfolio settings (stored in meta as JSON) ---
    _PORTFOLIO_DEFAULTS = {
        "max_concurrent": 5,
        "max_total_deployed_frac": 0.80,
        "portfolio_daily_loss_limit_pct": 0.08,
        "default_symbol": "",
        # --- decision brain config ---
        "brain_model": "qwen3.5:9b",
        "brain_ollama_url": "http://172.17.0.1:11434",
        "brain_confidence_threshold": 0.7,
        "brain_timeout_s": 30,
        "brain_autonomous_mode": False,
        "brain_auto_recommend": False,
    }

    def get_portfolio_settings(self) -> dict:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key='portfolio_settings'").fetchone()
        out = dict(self._PORTFOLIO_DEFAULTS)
        if row:
            out.update(json.loads(row[0]))
        return out

    def set_portfolio_settings(self, settings: dict) -> None:
        allowed = set(self._PORTFOLIO_DEFAULTS)
        bad = set(settings) - allowed
        if bad:
            raise ValueError(f"unknown portfolio settings: {sorted(bad)}")
        merged = self.get_portfolio_settings()
        merged.update(settings)
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('portfolio_settings', ?)",
            (json.dumps(merged),))
        self._conn.commit()

    def get_watchlist(self) -> list[str]:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key='watchlist'").fetchone()
        return json.loads(row[0]) if row else []

    def set_watchlist(self, symbols: list[str]) -> None:
        clean = [s for s in dict.fromkeys(symbols) if isinstance(s, str) and s]
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('watchlist', ?)",
            (json.dumps(clean),))
        self._conn.commit()

    def get_discord_webhook(self) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key='discord_webhook'").fetchone()
        return row[0] if row and row[0] else None

    def set_discord_webhook(self, url: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('discord_webhook', ?)",
            (url or "",))
        self._conn.commit()
