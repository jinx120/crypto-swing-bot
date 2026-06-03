from swingbot.universe import fallback_universe
from swingbot.profiles import ProfileStore


def test_fallback_universe_is_usd_pairs():
    u = fallback_universe()
    assert "BTC/USD" in u and "ETH/USD" in u
    assert all(s.endswith("/USD") for s in u)
    assert u == sorted(u)  # stable, sorted


def test_watchlist_roundtrip_and_default_empty(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    assert s.get_watchlist() == []
    s.set_watchlist(["ETH/USD", "BTC/USD"])
    assert s.get_watchlist() == ["ETH/USD", "BTC/USD"]


def test_default_symbol_setting(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    assert s.get_portfolio_settings()["default_symbol"] == ""
    s.set_portfolio_settings({"default_symbol": "ETH/USD"})
    assert s.get_portfolio_settings()["default_symbol"] == "ETH/USD"


def test_list_usd_pairs_filters_tradable_usd(monkeypatch):
    from swingbot.broker.alpaca import AlpacaBroker

    class _Asset:
        def __init__(self, symbol, tradable):
            self.symbol, self.tradable = symbol, tradable

    class _FakeClient:
        def get_all_assets(self, req):
            return [_Asset("BTC/USD", True), _Asset("ETH/USD", True),
                    _Asset("LUNA/USD", False), _Asset("BTC/USDT", True)]

    b = AlpacaBroker.__new__(AlpacaBroker)   # bypass __init__/network
    b._client = _FakeClient()
    assert b.list_usd_pairs() == ["BTC/USD", "ETH/USD"]
