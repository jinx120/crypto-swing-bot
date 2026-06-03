from __future__ import annotations

from swingbot.types import MarketContext, SignalResult


class FvgSignal:
    """ICT bullish Fair Value Gap signal (long-only discount entry).

    A bullish FVG is a 3-candle imbalance where the 3rd candle's low sits
    ABOVE the 1st candle's high, leaving an un-traded gap ``[high[1], low[3]]``
    created by a strong displacement candle in between. Price tends to retrace
    back DOWN into that gap, where it acts as support — ICT's "discount" long.

    Scoring (0..1, higher = stronger long):
      * find the most recent bullish FVG within ``lookback`` bars whose gap is
        at least ``min_gap_pct`` of price (filters noise / non-displacement),
      * 0 if price hasn't retraced yet (still above the gap top),
      * 0 if price has broken below the gap floor (gap filled / invalidated),
      * otherwise linear from 0 at the gap top to 1 at the gap floor, so a
        deeper retrace into the discount scores higher.
    """

    name = "fvg"

    def __init__(self, weight: float, lookback: int = 50, min_gap_pct: float = 0.0):
        self.weight = weight
        self.lookback = lookback
        self.min_gap_pct = min_gap_pct

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        df = ctx.candles
        n = len(df)
        if n < 3:
            return SignalResult(self.name, 0.0, {"reason": "warmup"})

        high = df["high"].to_numpy()
        low = df["low"].to_numpy()
        price = float(df["close"].iloc[-1])

        # scan newest -> oldest for the most recent qualifying bullish FVG.
        # i is the 3rd candle of the pattern (candles i-2, i-1, i).
        start = max(2, n - self.lookback)
        gap_low = gap_high = None
        for i in range(n - 1, start - 1, -1):
            gl = float(high[i - 2])
            gh = float(low[i])
            if gh <= gl:
                continue                     # no upward imbalance here
            if price > 0 and (gh - gl) / price < self.min_gap_pct:
                continue                     # gap too small to be displacement
            gap_low, gap_high = gl, gh
            break

        if gap_low is None:
            return SignalResult(self.name, 0.0, {"gap": None})

        meta = {"gap_low": gap_low, "gap_high": gap_high, "price": price}
        if price >= gap_high:
            return SignalResult(self.name, 0.0, {**meta, "state": "no_retrace"})
        if price <= gap_low:
            return SignalResult(self.name, 0.0, {**meta, "state": "invalidated"})

        score = (gap_high - price) / (gap_high - gap_low)
        score = max(0.0, min(1.0, score))
        return SignalResult(self.name, score, {**meta, "state": "in_gap"})
