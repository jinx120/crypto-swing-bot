from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone

from swingbot.journal import Trade
from swingbot.types import ExitReason, Regime, Side


class TradeStore:
    """Lock-protected durable closed-trade history keyed by confirmed exit order."""

    def __init__(self, db_path: str):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock, self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    exit_order_id TEXT PRIMARY KEY,
                    strategy TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    entry_order_id TEXT,
                    entry_ts TEXT NOT NULL,
                    exit_ts TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    qty REAL NOT NULL,
                    pnl REAL NOT NULL,
                    exit_reason TEXT NOT NULL,
                    score_at_entry REAL NOT NULL,
                    regime_at_entry TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_trades_strategy_exit
                ON trades(strategy, exit_ts, inserted_at)
                """
            )

    def record(
        self,
        strategy: str,
        trade: Trade,
        *,
        symbol: str,
        entry_order_id: str | None,
        exit_order_id: str,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO trades (
                    exit_order_id, strategy, symbol, entry_order_id,
                    entry_ts, exit_ts, side, entry_price, exit_price, qty, pnl,
                    exit_reason, score_at_entry, regime_at_entry, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    exit_order_id,
                    strategy,
                    symbol,
                    entry_order_id,
                    trade.entry_ts.isoformat(),
                    trade.exit_ts.isoformat(),
                    trade.side.value,
                    trade.entry_price,
                    trade.exit_price,
                    trade.qty,
                    trade.pnl,
                    trade.exit_reason.value,
                    trade.score_at_entry,
                    trade.regime_at_entry.value,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def list(self, strategy: str | None = None) -> list[Trade]:
        query = "SELECT * FROM trades"
        params = []
        if strategy is not None:
            query += " WHERE strategy = ?"
            params.append(strategy)
        query += " ORDER BY exit_ts, inserted_at, exit_order_id"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._from_row(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _from_row(row) -> Trade:
        return Trade(
            entry_ts=datetime.fromisoformat(row[4]),
            exit_ts=datetime.fromisoformat(row[5]),
            side=Side(row[6]),
            entry_price=row[7],
            exit_price=row[8],
            qty=row[9],
            pnl=row[10],
            exit_reason=ExitReason(row[11]),
            score_at_entry=row[12],
            regime_at_entry=Regime(row[13]),
        )
