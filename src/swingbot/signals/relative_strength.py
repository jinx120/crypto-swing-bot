from __future__ import annotations

from swingbot.indicators import lookback_return
from swingbot.types import MarketContext, SignalResult


class RelativeStrengthSignal:
    name = "relative_strength"

    def __init__(self, weight: float, band: float = 0.02, lookback: int = 96):
        self.weight = weight
        self.band = band
        self.lookback = lookback

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        if ctx.benchmark is None:
            return SignalResult(self.name, 0.5, {"rs": None})
        coin_ret = lookback_return(ctx.candles["close"], self.lookback)
        bench_ret = lookback_return(ctx.benchmark["close"], self.lookback)
        rs = coin_ret - bench_ret
        # map rs in [-band, band] -> [0, 1]; 0.5 == neutral
        score = max(0.0, min(1.0, (rs + self.band) / (2 * self.band)))
        return SignalResult(self.name, score, {"rs": float(rs)})
