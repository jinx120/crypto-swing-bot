from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from core_engine.contracts import JournalEvent


@dataclass(frozen=True)
class Report:
    open_position: dict | None
    realized_pnl: float
    unrealized_pnl: float
    wins: int
    losses: int
    closed: list[dict]


class EngineJournal:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, "
            "symbol TEXT, reason TEXT, payload TEXT)"
        )
        self._conn.commit()

    def log(self, event: JournalEvent) -> None:
        self._conn.execute(
            "INSERT INTO events (ts, kind, symbol, reason, payload) VALUES (?,?,?,?,?)",
            (event.ts.isoformat(), event.kind, event.symbol, event.reason,
             json.dumps(event.payload)),
        )
        self._conn.commit()

    def events(self, kind: str | None = None, limit: int = 200) -> list[JournalEvent]:
        sql = "SELECT ts, kind, symbol, reason, payload FROM events"
        args: tuple = ()
        if kind is not None:
            sql += " WHERE kind = ?"
            args = (kind,)
        sql += " ORDER BY id DESC LIMIT ?"
        args += (limit,)
        rows = self._conn.execute(sql, args).fetchall()
        return [
            JournalEvent(ts=datetime.fromisoformat(r[0]), kind=r[1], symbol=r[2],
                         reason=r[3], payload=json.loads(r[4]))
            for r in rows
        ]

    def closed_trades(self) -> list[dict]:
        return [e.payload for e in self.events(kind="pnl", limit=10_000)]

    def report(self) -> Report:
        pnls = self.closed_trades()
        wins = sum(1 for p in pnls if p.get("won") is True)
        losses = sum(1 for p in pnls if p.get("won") is False)
        realized = sum(float(p.get("realized", 0.0)) for p in pnls)
        opens = self.events(kind="order", limit=1)
        open_pos = opens[0].payload if opens and opens[0].payload.get("open") else None
        unrealized = float(open_pos.get("unrealized", 0.0)) if open_pos else 0.0
        return Report(open_position=open_pos, realized_pnl=realized,
                      unrealized_pnl=unrealized, wins=wins, losses=losses, closed=pnls)
