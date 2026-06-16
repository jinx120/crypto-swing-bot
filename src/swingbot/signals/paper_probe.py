from __future__ import annotations

from swingbot.types import MarketContext, SignalResult


class PaperProbeSignal:
    """Deterministic proof-of-life signal, not a trading strategy."""

    name = "paper_probe"

    def __init__(self, weight: float):
        self.weight = weight

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        return SignalResult(self.name, 1.0, {"probe": True})
