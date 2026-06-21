import pytest

from swingbot.data.ccxt_provider import CcxtProvider
from swingbot.data.provider_factory import provider_for
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


def test_provider_for_coinbase_needs_no_creds():
    prov = provider_for("coinbase", creds=None)
    assert isinstance(prov, CcxtProvider)
    assert prov.exchange_id == "coinbase"
    assert prov.map_symbol("BTC/USD") == "BTC/USD"


def test_provider_for_alpaca_uses_creds():
    class FakeCreds:
        def make_data(self):
            return "ALPACA_PROVIDER"

    assert provider_for("alpaca", creds=FakeCreds()) == "ALPACA_PROVIDER"


def test_provider_for_alpaca_without_creds_is_none():
    assert provider_for("alpaca", creds=None) is None


def test_ccxt_get_candles_multi_loops_per_symbol():
    class FakeCcxt(CcxtProvider):
        def get_candles(self, symbol, timeframe, lookback):
            return f"{symbol}:{timeframe}:{lookback}"

    p = FakeCcxt(exchange_id="coinbase", quote_map={})
    out = p.get_candles_multi(["BTC/USD", "ETH/USD"], "15m", 10)
    assert out == {"BTC/USD": "BTC/USD:15m:10", "ETH/USD": "ETH/USD:15m:10"}
