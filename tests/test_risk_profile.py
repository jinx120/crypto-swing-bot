import pytest

from swingbot.risk_profile import (
    RISK_LEVELS,
    DEFAULT_RISK_LEVEL,
    risk_params,
    apply_risk_level,
    DRAWDOWN_SENSITIVITY,
)


def test_levels_and_default():
    assert RISK_LEVELS == ("Conservative", "Moderate", "Aggressive")
    assert DEFAULT_RISK_LEVEL == "Moderate"


def test_risk_params_values_match_spec():
    assert risk_params("Conservative")["max_position_frac"] == 0.05
    assert risk_params("Moderate")["entry_threshold"] == 0.50
    assert risk_params("Aggressive")["max_concurrent"] == 4
    # sl/tp stored as positive magnitudes
    assert risk_params("Conservative")["sl_pct"] == 0.005
    assert risk_params("Aggressive")["tp_pct"] == 0.020


def test_risk_params_unknown_level_raises():
    with pytest.raises(ValueError):
        risk_params("YOLO")


def test_apply_risk_level_overwrites_only_risk_keys():
    profile = {
        "symbol": "BTC/USD",
        "signals": {"kronos_forecast": {"weight": 1.0}},
        "entry_threshold": 0.05,
        "max_position_frac": 0.25,
    }
    out = apply_risk_level(profile, "Conservative")
    assert out["symbol"] == "BTC/USD"  # untouched
    assert out["signals"] == {"kronos_forecast": {"weight": 1.0}}  # untouched
    assert out["entry_threshold"] == 0.70  # overwritten
    assert out["max_position_frac"] == 0.05  # overwritten
    assert profile["entry_threshold"] == 0.05  # original not mutated


def test_drawdown_sensitivity():
    assert DRAWDOWN_SENSITIVITY == {
        "Conservative": "HIGH",
        "Moderate": "MEDIUM",
        "Aggressive": "LOW",
    }
