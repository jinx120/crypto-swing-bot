from swingbot.exits import pct_bracket_levels
from swingbot.profile import StrategyProfile


def test_pct_bracket_levels():
    stop, tp = pct_bracket_levels(100.0, tp_pct=0.015, sl_pct=0.01)
    assert round(tp, 6) == 101.5
    assert round(stop, 6) == 99.0


def test_profile_defaults_atr_mode_with_pct_fields():
    p = StrategyProfile(symbol="BTC/USD")
    assert p.bracket_mode == "atr"
    assert p.tp_pct == 0.015 and p.sl_pct == 0.01


def test_profile_from_dict_round_trips_pct_mode():
    p = StrategyProfile.from_dict(
        {
            "symbol": "BTC/USD",
            "bracket_mode": "pct",
            "tp_pct": 0.02,
            "sl_pct": 0.012,
        }
    )
    assert p.bracket_mode == "pct" and p.tp_pct == 0.02 and p.sl_pct == 0.012
