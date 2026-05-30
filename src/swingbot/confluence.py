from __future__ import annotations

from swingbot.profile import StrategyProfile
from swingbot.signals.base import Signal
from swingbot.signals.fvg import FvgSignal
from swingbot.signals.kronos_forecast import KronosForecastSignal
from swingbot.signals.oversold import OversoldSignal
from swingbot.signals.relative_strength import RelativeStrengthSignal
from swingbot.signals.vwap import VwapSignal
from swingbot.types import ConfluenceResult, MarketContext

_REGISTRY = {
    "oversold": OversoldSignal,
    "vwap": VwapSignal,
    "relative_strength": RelativeStrengthSignal,
    "fvg": FvgSignal,
    "kronos_forecast": KronosForecastSignal,
}


def build_signals(profile: StrategyProfile) -> list[Signal]:
    signals: list[Signal] = []
    for name, params in profile.signals.items():
        cls = _REGISTRY[name]
        signals.append(cls(**params))
    return signals


class ConfluenceEngine:
    def __init__(self, signals: list[Signal], profile: StrategyProfile):
        self.signals = signals
        self.profile = profile

    def evaluate(self, ctx: MarketContext) -> ConfluenceResult:
        results = {s.name: s.evaluate(ctx) for s in self.signals}
        contributions = {name: r.score * self._weight(name) for name, r in results.items()}
        score = sum(contributions.values())
        threshold = self.profile.entry_threshold
        return ConfluenceResult(
            score=score,
            threshold=threshold,
            passed=score >= threshold,
            contributions=contributions,
            signals=results,
        )

    def _weight(self, name: str) -> float:
        return self.profile.signals[name].get("weight", 0.0)
