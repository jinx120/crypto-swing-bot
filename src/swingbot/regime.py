from __future__ import annotations

from swingbot.indicators import sma
from swingbot.profile import StrategyProfile
from swingbot.types import MarketContext, Regime, RegimeResult


class RegimeFilter:
    def __init__(self, profile: StrategyProfile):
        self.profile = profile

    def evaluate(self, ctx: MarketContext) -> RegimeResult:
        df = ctx.htf if ctx.htf is not None else ctx.candles
        ma = sma(df["close"], self.profile.regime_ma_period)
        if len(ma) < 2:
            return RegimeResult(Regime.NEUTRAL, {"ma": None})
        ma_now, ma_prev = ma.iloc[-1], ma.iloc[-2]
        price = df["close"].iloc[-1]
        if ma_now != ma_now:  # NaN during warmup -> treat as neutral
            return RegimeResult(Regime.NEUTRAL, {"ma": None})
        rising = ma_now > ma_prev
        if price > ma_now and rising:
            regime = Regime.UPTREND
        elif price < ma_now and not rising:
            regime = Regime.DOWNTREND
        else:
            regime = Regime.NEUTRAL
        return RegimeResult(regime, {"ma": float(ma_now), "price": float(price)})

    def permits_entry(self, regime: Regime) -> bool:
        return regime in self.profile.allowed_regimes
