from __future__ import annotations

from datetime import datetime
from typing import Protocol

from swingbot.types import BrokerOrder, Regime


class Broker(Protocol):
    def open_long(
        self, ts: datetime, price: float, qty: float, stop: float, tp: float,
        max_hold_until: datetime, score_at_entry: float, regime_at_entry: Regime,
    ) -> None: ...

    def equity(self, mark_price: float) -> float: ...

    def submit_market_buy(
        self, symbol: str, qty: float, client_order_id: str
    ) -> BrokerOrder: ...

    def submit_market_sell(
        self, symbol: str, qty: float, client_order_id: str
    ) -> BrokerOrder: ...

    def get_order(
        self, order_id: str | None = None, client_order_id: str | None = None
    ) -> BrokerOrder | None: ...

    def get_position(self, symbol: str) -> dict | None: ...
