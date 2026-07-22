from __future__ import annotations

from dataclasses import dataclass

from swingbot.risk_profile import risk_params

_POS_FRAC_MULT = 0.7
_THRESH_MULT = 1.2
_SUSPEND_THRESHOLD = 999.0

_TIGHTEN_24H = 0.03
_SUSPEND_7D = 0.08
_RECOVER_24H = 0.01
_RECOVER_7D = 0.04

_STATUS = {
    0: "",
    1: "Defensive mode -- recovering from recent losses.",
    2: "Defensive mode -- new trades paused while recovering.",
}


@dataclass(frozen=True)
class TuneDecision:
    tier: int
    defensive: bool
    status: str
    params: dict


class AutoTuner:
    """Pure drawdown-to-tier policy; callers own I/O and persistence."""

    def decide(
        self,
        level: str,
        dd_24h: float,
        dd_7d: float,
        current_tier: int = 0,
    ) -> TuneDecision:
        tier = int(current_tier)
        if dd_7d > _SUSPEND_7D:
            tier = 2
        elif dd_24h > _TIGHTEN_24H:
            tier = max(tier, 1)
        if tier == 2 and dd_7d < _RECOVER_7D and dd_24h < _RECOVER_24H:
            tier = 1
        if tier == 1 and dd_24h < _RECOVER_24H and dd_7d < _RECOVER_7D:
            tier = 0

        base = risk_params(level)
        params = dict(base)
        if tier >= 1:
            params["max_position_frac"] = round(
                base["max_position_frac"] * _POS_FRAC_MULT, 6
            )
            params["entry_threshold"] = round(base["entry_threshold"] * _THRESH_MULT, 6)
            params["max_concurrent"] = max(1, base["max_concurrent"] - 1)
        if tier == 2:
            params["entry_threshold"] = _SUSPEND_THRESHOLD
        return TuneDecision(
            tier=tier,
            defensive=tier >= 1,
            status=_STATUS[tier],
            params=params,
        )
