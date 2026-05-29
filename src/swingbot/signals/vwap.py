from __future__ import annotations

from swingbot.indicators import rolling_vwap
from swingbot.types import MarketContext, SignalResult


class VwapSignal:
    name = "vwap"

    def __init__(self, weight: float, window: int = 96, max_dist: float = 0.03):
        self.weight = weight
        self.window = window
        self.max_dist = max_dist

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        vwap = rolling_vwap(ctx.candles, self.window).iloc[-1]
        price = ctx.candles["close"].iloc[-1]
        if vwap != vwap:  # NaN during warmup
            return SignalResult(self.name, 0.0, {"vwap": None})
        dist = (vwap - price) / vwap          # positive when price below vwap
        score = max(0.0, min(1.0, dist / self.max_dist))
        return SignalResult(self.name, score, {"vwap": float(vwap), "dist": float(dist)})
