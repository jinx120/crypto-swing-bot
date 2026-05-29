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
    def __init__(self):
        self.trades: list[Trade] = []

    def record(self, trade: Trade) -> None:
        self.trades.append(trade)
