from __future__ import annotations

from swingbot.types import MarketContext, SignalResult

# A constant window still leaves a float residual in the mean, so pandas'
# std() returns ~1e-19 rather than 0.0. Real premium/funding series carry
# values of order 1e-4..1e-2 and vary by >= ~1e-6, so this cutoff sits far
# below any genuine variation and far above the residual.
ZERO_STD_EPS = 1e-12


class PremiumFlowSignal:
    """Exchange-flow pressure via the Coinbase premium (spec 6c substitute).

    Spec 6c called for on-chain exchange net flow, which has no free data source.
    The Coinbase premium - US spot price against offshore USDT price - proxies the
    same pressure: a premium means US demand is lifting offers (accumulation, the
    on-chain "outflow" case), a discount means US supply is hitting bids
    (distribution, the "inflow" case).

    The raw premium drifts with venue basis, so the level is meaningless on its
    own; what matters is where it sits relative to its own recent range. The score
    is therefore the z-score over `lookback` bars mapped through +/- `band`
    standard deviations onto 0..1.

    Insufficient history, a flat series, or a missing feed all score a neutral 0.5
    rather than vetoing entries on a data problem.
    """

    name = "premium_flow"

    def __init__(self, weight: float, lookback: int = 180, band: float = 2.0,
                 series_key: str = "cb_premium"):
        if band <= 0:
            raise ValueError("band must be positive")
        if lookback < 2:
            raise ValueError("lookback must be at least 2")
        self.weight = weight
        self.lookback = lookback
        self.band = band
        self.series_key = series_key

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        series = (ctx.extras or {}).get(self.series_key)
        if series is None or len(series) == 0:
            return SignalResult(self.name, 0.5,
                                {self.series_key: None, "error": "no_data"})
        window = series["value"].iloc[-self.lookback:]
        if len(window) < self.lookback:
            return SignalResult(self.name, 0.5,
                                {self.series_key: float(window.iloc[-1]),
                                 "error": "insufficient_history"})
        std = float(window.std())          # ddof=1, matching the lab harness
        latest = float(window.iloc[-1])
        if not (std > ZERO_STD_EPS):
            return SignalResult(self.name, 0.5,
                                {self.series_key: latest, "error": "zero_variance"})
        z = (latest - float(window.mean())) / std
        score = max(0.0, min(1.0, (z + self.band) / (2 * self.band)))
        return SignalResult(self.name, score, {self.series_key: latest, "z": z})
