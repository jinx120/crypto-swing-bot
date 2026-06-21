import pytest
from swingbot.profiles import ProfileStore


def _p(symbol="TRX/USD", thr=0.3):
    return {"symbol": symbol,
            "signals": {"oversold": {"weight": 1.0, "oversold_level": 45}},
            "entry_threshold": thr}


def test_save_get_list_delete(tmp_path):
    s = ProfileStore(str(tmp_path / "db.sqlite"))
    assert s.list() == []
    s.save("trx", _p())
    assert s.list() == ["trx"]
    assert s.get("trx")["symbol"] == "TRX/USD"
    s.delete("trx")
    assert s.list() == []
    assert s.get("trx") is None


def test_active_pointer(tmp_path):
    s = ProfileStore(str(tmp_path / "db.sqlite"))
    assert s.get_active_name() is None
    s.save("trx", _p())
    s.set_active("trx")
    assert s.get_active_name() == "trx"
    assert s.get_active()["symbol"] == "TRX/USD"


def test_save_rejects_invalid_profile(tmp_path):
    s = ProfileStore(str(tmp_path / "db.sqlite"))
    with pytest.raises(ValueError):
        s.save("bad", {"signals": {}})


def test_set_active_unknown_raises(tmp_path):
    s = ProfileStore(str(tmp_path / "db.sqlite"))
    with pytest.raises(ValueError):
        s.set_active("nope")


def test_rebalance_settings_round_trip_and_merge(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    s.set_rebalance_settings({"enabled": True, "mode": "hard"})
    s.set_rebalance_settings({"drift_threshold": 0.1})
    got = s.get_rebalance_settings()
    assert got["enabled"] is True and got["mode"] == "hard"
    assert got["drift_threshold"] == 0.1


def test_rebalance_targets_round_trip(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    s.set_rebalance_targets({"a": 0.3, "b": 0.4})
    assert s.get_rebalance_targets() == {"a": 0.3, "b": 0.4}


def test_rebalance_targets_reject_sum_over_one(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    with pytest.raises(ValueError):
        s.set_rebalance_targets({"a": 0.7, "b": 0.5})


def test_risk_dial_defaults_and_validates(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    assert s.get_risk_dial() == "balanced"
    s.set_risk_dial("cautious")
    assert s.get_risk_dial() == "cautious"
    with pytest.raises(ValueError):
        s.set_risk_dial("wild")
