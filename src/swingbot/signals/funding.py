from __future__ import annotations

from swingbot.types import MarketContext, SignalResult


class FundingMeanReversionSignal:
    """Perpetual funding as a long-entry filter (spec 6b).

    Sustained positive funding means longs are paying shorts: the perp is crowded
    long and price often snaps back, so this is a bad moment to add another long.
    Negative funding means shorts are paying: crowded short, and squeezes resolve
    upward. The bot is long-only, so the signal expresses the bearish case as a
    score near 0 rather than as a short.

    score = clamp((high_thresh - funding) / (high_thresh - low_thresh), 0, 1)

    Defaults follow the spec: 8h funding at or above +0.05% scores 0, at or below
    -0.01% scores 1. A missing reading scores a neutral 0.5 - the funding feed is
    third-party, and an outage must not silently veto every entry.
    """

    name = "funding_mr"

    def __init__(self, weight: float, high_thresh: float = 0.0005,
                 low_thresh: float = -0.0001, series_key: str = "funding_8h"):
        if high_thresh <= low_thresh:
            raise ValueError("high_thresh must be greater than low_thresh")
        self.weight = weight
        self.high_thresh = high_thresh
        self.low_thresh = low_thresh
        self.series_key = series_key

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        series = (ctx.extras or {}).get(self.series_key)
        if series is None or len(series) == 0:
            return SignalResult(self.name, 0.5,
                                {self.series_key: None, "error": "no_data"})
        funding = float(series["value"].iloc[-1])
        if funding != funding:  # NaN
            return SignalResult(self.name, 0.5,
                                {self.series_key: None, "error": "no_data"})
        span = self.high_thresh - self.low_thresh
        score = max(0.0, min(1.0, (self.high_thresh - funding) / span))
        return SignalResult(self.name, score, {self.series_key: funding})
