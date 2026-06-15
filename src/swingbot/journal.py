from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from swingbot.types import ExitReason, Regime, Side


@dataclass
class Trade:
    entry_ts: datetime
    exit_ts: datetime
    side: Side
    entry_price: float
    exit_price: float
    qty: float
    pnl: float                 # net of fees, in account currency
    exit_reason: ExitReason
    score_at_entry: float
    regime_at_entry: Regime


class TradeJournal:
    def __init__(self, store=None, strategy: str | None = None):
        if store is not None and strategy is None:
            raise ValueError("durable TradeJournal requires a strategy")
        self._store = store
        self._strategy = strategy
        self._trades: list[Trade] = []

    @property
    def trades(self) -> list[Trade]:
        if self._store is not None:
            return self._store.list(strategy=self._strategy)
        return self._trades

    def record(
        self,
        trade: Trade,
        *,
        symbol: str | None = None,
        entry_order_id: str | None = None,
        exit_order_id: str | None = None,
    ) -> None:
        if self._store is None:
            self._trades.append(trade)
            return
        if symbol is None or exit_order_id is None:
            raise ValueError("durable trade record requires symbol and exit_order_id")
        self._store.record(
            self._strategy,
            trade,
            symbol=symbol,
            entry_order_id=entry_order_id,
            exit_order_id=exit_order_id,
        )
