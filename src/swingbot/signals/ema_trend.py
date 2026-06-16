from __future__ import annotations

from swingbot.indicators import ema
from swingbot.types import MarketContext, SignalResult


class EmaTrendSignal:
    """Honest trend signal: long bias when the fast EMA leads the slow EMA.

    score = clamp(spread / band, 0, 1), where spread = (ema_fast - ema_slow) / ema_slow.
    A non-positive spread scores 0; warmup NaNs score 0.
    """

    name = "ema_trend"

    def __init__(self, weight: float, fast: int = 12, slow: int = 26, band: float = 0.01):
        if fast >= slow:
            raise ValueError("fast period must be < slow period")
        self.weight = weight
        self.fast = fast
        self.slow = slow
        self.band = band

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        close = ctx.candles["close"]
        ef = ema(close, self.fast).iloc[-1]
        es = ema(close, self.slow).iloc[-1]
        if ef != ef or es != es or es == 0:
            return SignalResult(
                self.name,
                0.0,
                {"ema_fast": None, "ema_slow": None, "spread": None},
            )
        spread = (ef - es) / es
        score = max(0.0, min(1.0, spread / self.band))
        return SignalResult(
            self.name,
            score,
            {"ema_fast": float(ef), "ema_slow": float(es), "spread": float(spread)},
        )
