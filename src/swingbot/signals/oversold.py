from __future__ import annotations

from swingbot.indicators import rsi
from swingbot.types import MarketContext, SignalResult


class OversoldSignal:
    name = "oversold"

    def __init__(self, weight: float, oversold_level: float = 30.0, period: int = 14):
        self.weight = weight
        self.oversold_level = oversold_level
        self.period = period

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        value = rsi(ctx.candles["close"], self.period).iloc[-1]
        if value != value:  # NaN during warmup
            return SignalResult(self.name, 0.0, {"rsi": None})
        # score: 0 at/above the level, ramps to 1 as rsi -> 0
        score = max(0.0, min(1.0, (self.oversold_level - value) / self.oversold_level))
        return SignalResult(self.name, score, {"rsi": float(value)})
