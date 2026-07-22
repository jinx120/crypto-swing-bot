from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone


class EquitySnapshotStore:
    """Append-only portfolio-equity time-series for drawdown and P&L windows."""

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS equity_snapshots "
            "(ts TEXT NOT NULL, equity REAL NOT NULL)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity_snapshots(ts)"
        )
        self._conn.commit()

    def record(self, equity: float, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._conn.execute(
            "INSERT INTO equity_snapshots (ts, equity) VALUES (?, ?)",
            (now.isoformat(), float(equity)),
        )
        self._conn.commit()

    def _window(self, hours: float, now: datetime | None) -> list[float]:
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=hours)).isoformat()
        rows = self._conn.execute(
            "SELECT equity FROM equity_snapshots WHERE ts >= ? ORDER BY ts",
            (cutoff,),
        ).fetchall()
        return [r[0] for r in rows]

    def drawdown(self, hours: float, now: datetime | None = None) -> float:
        """Return current equity's fractional drawdown from the rolling-window peak."""
        eqs = self._window(hours, now)
        if not eqs:
            return 0.0
        peak = max(eqs)
        current = eqs[-1]
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - current) / peak)

    def pnl_window(self, hours: float, now: datetime | None = None) -> tuple[float, float]:
        """Return absolute and fractional P&L from window-start equity to latest equity."""
        eqs = self._window(hours, now)
        if len(eqs) < 2:
            return 0.0, 0.0
        start, current = eqs[0], eqs[-1]
        abs_pnl = current - start
        pct = (abs_pnl / start) if start else 0.0
        return abs_pnl, pct

    def prune(self, keep_days: float = 30.0, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=keep_days)).isoformat()
        self._conn.execute("DELETE FROM equity_snapshots WHERE ts < ?", (cutoff,))
        self._conn.commit()
