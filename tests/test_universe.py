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
