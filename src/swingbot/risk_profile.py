from __future__ import annotations

# The three named risk levels the user picks on the Coins screen. Each maps to a
# full internal StrategyProfile param set (spec §5a). The user never sees the
# numbers -- they pick a name. Only the risk-controlled keys are defined here;
# symbol/signals/timeframe/etc. stay on the per-coin profile.
RISK_LEVELS = ("Conservative", "Moderate", "Aggressive")
DEFAULT_RISK_LEVEL = "Moderate"

_PARAMS: dict[str, dict] = {
    "Conservative": {
        "max_position_frac": 0.05,
        "entry_threshold": 0.70,
        "tp_pct": 0.008,
        "sl_pct": 0.005,
        "max_concurrent": 1,
        "cooldown_minutes": 60,
    },
    "Moderate": {
        "max_position_frac": 0.10,
        "entry_threshold": 0.50,
        "tp_pct": 0.012,
        "sl_pct": 0.008,
        "max_concurrent": 2,
        "cooldown_minutes": 30,
    },
    "Aggressive": {
        "max_position_frac": 0.20,
        "entry_threshold": 0.30,
        "tp_pct": 0.020,
        "sl_pct": 0.015,
        "max_concurrent": 4,
        "cooldown_minutes": 0,
    },
}

# Consumed by the AutoTuner (how aggressively to react to drawdown), NOT written
# to the strategy profile.
DRAWDOWN_SENSITIVITY = {
    "Conservative": "HIGH",
    "Moderate": "MEDIUM",
    "Aggressive": "LOW",
}


def risk_params(level: str) -> dict:
    """The risk-controlled param overlay for a named level. Fresh dict each call."""
    if level not in _PARAMS:
        raise ValueError(f"unknown risk level {level!r}")
    return dict(_PARAMS[level])


def apply_risk_level(profile: dict, level: str) -> dict:
    """Return a copy of profile with the level's risk params applied."""
    merged = dict(profile)
    merged.update(risk_params(level))
    return merged
