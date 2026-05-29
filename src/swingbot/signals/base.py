from __future__ import annotations

from typing import Protocol

from swingbot.types import MarketContext, SignalResult


class Signal(Protocol):
    name: str
    weight: float

    def evaluate(self, ctx: MarketContext) -> SignalResult: ...
