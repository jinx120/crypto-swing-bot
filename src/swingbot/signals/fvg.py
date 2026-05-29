from __future__ import annotations

from swingbot.types import MarketContext, SignalResult


class FvgSignal:
    """Fair Value Gap signal. Interface only in Phase 1; returns neutral 0.

    Implemented in a later phase. Defined now so the confluence engine and
    profiles can reference it without code changes when it lands.
    """

    name = "fvg"

    def __init__(self, weight: float):
        self.weight = weight

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        return SignalResult(self.name, 0.0, {"implemented": False})
