import pytest
from swingbot.profiles import ProfileStore


def _p(symbol="TRX/USD"):
    return {"symbol": symbol, "signals": {"oversold": {"weight": 1.0}}, "entry_threshold": 0.3}


def test_arm_disarm_and_list(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    s.save("btc", _p("BTC/USD")); s.save("eth", _p("ETH/USD"))
    assert s.list_armed() == []
    s.arm("btc"); s.arm("eth")
    assert set(s.list_armed()) == {"btc", "eth"}
    assert s.is_armed("btc") is True
    s.disarm("btc")
    assert s.list_armed() == ["eth"]


def test_arm_unknown_raises(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    with pytest.raises(ValueError):
        s.arm("nope")


def test_live_eligible_flag(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    s.save("btc", _p("BTC/USD")); s.arm("btc")
    assert s.is_live_eligible("btc") is False
    s.set_live_eligible("btc", True)
    assert s.is_live_eligible("btc") is True
    flags = {f["name"]: f["live_eligible"] for f in s.armed_with_flags()}
    assert flags == {"btc": True}


def test_active_migrates_into_armed(tmp_path):
    path = str(tmp_path / "p.db")
    s = ProfileStore(path)
    s.save("btc", _p("BTC/USD")); s.set_active("btc")
    # reopen: migration seeds armed from the legacy active pointer
    s2 = ProfileStore(path)
    assert "btc" in s2.list_armed()


def test_portfolio_settings_defaults_and_override(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    d = s.get_portfolio_settings()
    assert d["max_concurrent"] == 5 and d["max_total_deployed_frac"] == 0.80
    s.set_portfolio_settings({"max_concurrent": 8})
    assert s.get_portfolio_settings()["max_concurrent"] == 8
    assert s.get_portfolio_settings()["max_total_deployed_frac"] == 0.80  # unchanged keys persist
