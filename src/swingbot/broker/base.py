from __future__ import annotations

from datetime import datetime
from typing import Protocol

from swingbot.types import Regime


class Broker(Protocol):
    def open_long(
        self, ts: datetime, price: float, qty: float, stop: float, tp: float,
        max_hold_until: datetime, score_at_entry: float, regime_at_entry: Regime,
    ) -> None: ...

    def equity(self, mark_price: float) -> float: ...
