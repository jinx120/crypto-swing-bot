from swingbot.managed_profiles import (
    MANAGED_LABELS,
    MANAGED_PROFILE_NAMES,
    MANAGED_VERSION,
    managed_definitions,
)
from swingbot.profile import StrategyProfile


def test_strategy_definitions_present_and_reproducible():
    a = managed_definitions(enable_probe=False)
    b = managed_definitions(enable_probe=False)
    assert a == b
    assert set(a) == {"btc_trend", "eth_trend"}
    assert "paper_probe" not in a


def test_probe_included_only_when_enabled():
    with_probe = managed_definitions(enable_probe=True)
    assert "paper_probe" in with_probe
    assert with_probe["paper_probe"]["signals"] == {"paper_probe": {"weight": 1.0}}


def test_definitions_are_valid_profiles():
    for pdict in managed_definitions(enable_probe=True).values():
        StrategyProfile.from_dict(pdict)


def test_trend_profiles_use_ema_trend_signal():
    defs = managed_definitions(enable_probe=False)
    assert "ema_trend" in defs["btc_trend"]["signals"]
    assert defs["eth_trend"]["symbol"] == "ETH/USD"


def test_probe_allows_all_regimes_so_it_can_fire():
    probe = managed_definitions(enable_probe=True)["paper_probe"]
    assert set(probe["allowed_regimes"]) == {"uptrend", "neutral", "downtrend"}


def test_names_and_labels_cover_all_managed():
    assert MANAGED_PROFILE_NAMES == {"btc_trend", "eth_trend", "paper_probe"}
    assert MANAGED_LABELS["paper_probe"]["kind"] == "probe"
    assert MANAGED_LABELS["btc_trend"]["kind"] == "strategy"
    assert isinstance(MANAGED_VERSION, int)
