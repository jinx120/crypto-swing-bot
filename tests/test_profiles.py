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
