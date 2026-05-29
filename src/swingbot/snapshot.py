from __future__ import annotations

from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.profile import StrategyProfile
from swingbot.regime import RegimeFilter
from swingbot.types import MarketContext


def signal_snapshot(profile: StrategyProfile, ctx: MarketContext) -> dict:
    """Compute the current regime + confluence breakdown for DISPLAY only."""
    regime = RegimeFilter(profile)
    reg = regime.evaluate(ctx)
    conf = ConfluenceEngine(build_signals(profile), profile).evaluate(ctx)
    return {
        "regime": reg.regime.value,
        "permitted": regime.permits_entry(reg.regime),
        "score": conf.score,
        "threshold": conf.threshold,
        "passed": bool(conf.passed),
        "contributions": conf.contributions,
        "signals": {name: {"score": r.score, "meta": r.meta}
                    for name, r in conf.signals.items()},
    }
