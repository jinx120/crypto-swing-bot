import pytest

from swingbot.profiles import ProfileStore


def _store(tmp_path):
    return ProfileStore(str(tmp_path / "swingbot.db"))


def test_data_source_defaults_to_coinbase(tmp_path):
    assert _store(tmp_path).get_data_source() == "coinbase"


def test_data_source_round_trips(tmp_path):
    s = _store(tmp_path)
    s.set_data_source("kraken")
    assert s.get_data_source() == "kraken"


def test_data_source_rejects_unknown(tmp_path):
    with pytest.raises(ValueError):
        _store(tmp_path).set_data_source("binance")
