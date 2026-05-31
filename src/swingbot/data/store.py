from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pandas as pd

_DDL = """
CREATE TABLE IF NOT EXISTS bars (
    symbol    TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts        INTEGER NOT NULL,
    open      REAL NOT NULL,
    high      REAL NOT NULL,
    low       REAL NOT NULL,
    close     REAL NOT NULL,
    volume    REAL NOT NULL,
    PRIMARY KEY (symbol, timeframe, ts)
);
"""


class CandleStore:
    """SQLite-backed OHLC candle store. One row per (symbol, timeframe, bar).

    `ts` is stored as UTC epoch seconds so the frontend chart (TradingView
    Lightweight Charts) can consume it directly as its `time` field.
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

    def upsert_df(self, symbol: str, timeframe: str, df: pd.DataFrame) -> int:
        """Insert/replace bars from a DataFrame with columns
        ts, open, high, low, close, volume (ts = UTC pandas Timestamp)."""
        if df is None or df.empty:
            return 0
        rows = [
            (symbol, timeframe, int(r.ts.timestamp()),
             float(r.open), float(r.high), float(r.low),
             float(r.close), float(r.volume))
            for r in df.itertuples(index=False)
        ]
        with self._lock, self._connect() as con:
            con.executemany(
                "INSERT OR REPLACE INTO bars "
                "(symbol, timeframe, ts, open, high, low, close, volume) "
                "VALUES (?,?,?,?,?,?,?,?)",
                rows,
            )
        return len(rows)

    def get(self, symbol: str, timeframe: str, limit: int = 500) -> list[dict]:
        """Return up to `limit` most recent bars, oldest-first."""
        with self._lock, self._connect() as con:
            cur = con.execute(
                "SELECT ts, open, high, low, close, volume FROM bars "
                "WHERE symbol=? AND timeframe=? ORDER BY ts DESC LIMIT ?",
                (symbol, timeframe, limit),
            )
            rows = cur.fetchall()
        rows.reverse()
        return [
            {"time": ts, "open": o, "high": h, "low": lo, "close": c, "volume": v}
            for ts, o, h, lo, c, v in rows
        ]

    def symbols(self) -> list[dict]:
        with self._lock, self._connect() as con:
            cur = con.execute("SELECT DISTINCT symbol, timeframe FROM bars")
            return [{"symbol": s, "timeframe": tf} for s, tf in cur.fetchall()]
