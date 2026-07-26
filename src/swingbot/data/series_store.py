from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pandas as pd

_DDL = """
CREATE TABLE IF NOT EXISTS series (
    name   TEXT NOT NULL,
    symbol TEXT NOT NULL,
    ts     INTEGER NOT NULL,
    value  REAL NOT NULL,
    PRIMARY KEY (name, symbol, ts)
);
"""

_EMPTY = pd.DataFrame({"ts": pd.Series(dtype="datetime64[ns, UTC]"),
                       "value": pd.Series(dtype="float64")})


class SeriesStore:
    """SQLite store for non-price time series (funding rates, premium spreads).

    One row per (series name, symbol, timestamp). `ts` is UTC epoch seconds, the
    same convention as CandleStore, so the two can be joined without conversion.
    """

    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as con:
            con.execute(_DDL)

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=10)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def upsert(self, name: str, symbol: str, rows: list[tuple[int, float]]) -> int:
        """Insert/replace (ts, value) pairs. Re-running an ingest is safe."""
        if not rows:
            return 0
        payload = [(name, symbol, int(ts), float(value)) for ts, value in rows]
        with self._lock, self._connect() as con:
            con.executemany(
                "INSERT OR REPLACE INTO series (name, symbol, ts, value) VALUES (?,?,?,?)",
                payload,
            )
        return len(payload)

    def get_df(self, name: str, symbol: str, start_ts: int | None = None,
               end_ts: int | None = None) -> pd.DataFrame:
        """Oldest-first (ts, value) frame with tz-aware UTC timestamps."""
        sql = "SELECT ts, value FROM series WHERE name=? AND symbol=?"
        params: list = [name, symbol]
        if start_ts is not None:
            sql += " AND ts>=?"
            params.append(int(start_ts))
        if end_ts is not None:
            sql += " AND ts<=?"
            params.append(int(end_ts))
        sql += " ORDER BY ts"
        with self._lock, self._connect() as con:
            rows = con.execute(sql, params).fetchall()
        if not rows:
            return _EMPTY.copy()
        df = pd.DataFrame(rows, columns=["ts", "value"])
        df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
        df["value"] = df["value"].astype(float)
        return df

    def coverage(self, name: str, symbol: str) -> dict:
        with self._lock, self._connect() as con:
            min_ts, max_ts, count = con.execute(
                "SELECT MIN(ts), MAX(ts), COUNT(*) FROM series WHERE name=? AND symbol=?",
                (name, symbol),
            ).fetchone()
        return {"min_ts": min_ts, "max_ts": max_ts, "count": count}

    def names(self) -> list[dict]:
        with self._lock, self._connect() as con:
            rows = con.execute("SELECT DISTINCT name, symbol FROM series").fetchall()
        return [{"name": n, "symbol": s} for n, s in rows]
