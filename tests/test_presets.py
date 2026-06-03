import pytest

from swingbot.presets import ARCHETYPES, archetype_profile, build_candidates
from swingbot.profile import StrategyProfile


def test_archetypes_have_required_fields():
    keys = {a.key for a in ARCHETYPES}
    assert keys == {"conservative", "balanced", "aggressive", "ai_kronos", "ict_fvg"}
    for a in ARCHETYPES:
        assert a.name and a.description and a.signals


def test_archetype_profile_is_valid_and_overrides_symbol():
    bal = next(a for a in ARCHETYPES if a.key == "balanced")
    p = archetype_profile(bal, symbol="ETH/USD")
    StrategyProfile.from_dict(p)          # must not raise
    assert p["symbol"] == "ETH/USD"
    assert "oversold" in p["signals"] and "vwap" in p["signals"]


def test_ict_fvg_archetype_profile_uses_fvg_signal():
    fvg = next(a for a in ARCHETYPES if a.key == "ict_fvg")
    p = archetype_profile(fvg, symbol="BTC/USD")
    StrategyProfile.from_dict(p)          # must not raise
    assert "fvg" in p["signals"]
    assert p["signals"]["fvg"]["weight"] == 0.5
    assert "oversold" in p["signals"] and "vwap" in p["signals"]


def test_build_candidates_non_ai():
    cs = build_candidates("TRX/USD", "balanced", "swing", ai=False)
    assert 1 <= len(cs) <= 6
    for c in cs:
        StrategyProfile.from_dict(c["profile"])
        assert "kronos_forecast" not in c["profile"]["signals"]
        assert c["profile"]["symbol"] == "TRX/USD"
        assert c["profile"]["timeframe"] == "15m"     # swing


def test_build_candidates_ai_includes_kronos():
    cs = build_candidates("TRX/USD", "aggressive", "scalp", ai=True)
    assert 1 <= len(cs) <= 3
    assert all("kronos_forecast" in c["profile"]["signals"] for c in cs)
    assert all(c["profile"]["timeframe"] == "5m" for c in cs)   # scalp


def test_build_candidates_rejects_bad_knobs():
    with pytest.raises(ValueError):
        build_candidates("TRX/USD", "nope", "swing")
    with pytest.raises(ValueError):
        build_candidates("TRX/USD", "balanced", "nope")
