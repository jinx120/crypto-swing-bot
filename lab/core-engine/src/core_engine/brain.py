from __future__ import annotations
from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.regime import RegimeFilter
from swingbot.types import MarketContext
from core_engine.contracts import Action, Decision


def decide(ctx: MarketContext, has_position: bool, *, profile, kronos) -> Decision:
    """Pure long-only entry decision. Exits are handled separately."""
    if has_position:
        return Decision(Action.HOLD, 0.0, "already in position", {})

    regime_filter = RegimeFilter(profile)
    regime = regime_filter.evaluate(ctx)
    if not regime_filter.permits_entry(regime.regime):
        return Decision(Action.HOLD, 0.0, f"regime gate blocks entry: {regime.regime}",
                        {"regime": regime.regime})

    conf = ConfluenceEngine(build_signals(profile), profile).evaluate(ctx)
    kron = kronos.evaluate(ctx).score if kronos is not None else 0.0
    if not conf.passed:
        return Decision(Action.HOLD, conf.score,
                        f"confluence {conf.score:.2f} < {conf.threshold:.2f}",
                        {"confluence": conf.score, "kronos": kron})

    confidence = min(1.0, 0.5 * conf.score + 0.5 * kron)
    return Decision(Action.ENTER_LONG, confidence,
                    f"confluence pass {conf.score:.2f}, kronos {kron:.2f}",
                    {"confluence": conf.score, "kronos": kron, "regime": regime.regime})
