from fastapi.testclient import TestClient

from swingbot.web import create_app


class FakeProvider:
    def __init__(self): self.calls = 0
    def get_latest_prices(self, symbols):
        self.calls += 1
        return {s: 100.0 + i for i, s in enumerate(symbols)}


class FakeMarket:
    def __init__(self): self.prov = FakeProvider()
    def _provider(self): return self.prov


class _Ctl:
    def status(self): return {}


def _client(market):
    app = create_app(_Ctl(), profiles=None, creds=None, token="t", market=market)
    return TestClient(app)


def test_price_returns_cached_quotes():
    market = FakeMarket()
    c = _client(market)
    r = c.get("/api/price?symbols=BTC/USD,ETH/USD")
    assert r.status_code == 200
    body = r.json()
    assert body["BTC/USD"]["price"] == 100.0
    assert body["ETH/USD"]["price"] == 101.0
    assert body["BTC/USD"]["stale"] is False
    # second immediate call is served from the 2s cache (no extra upstream call)
    c.get("/api/price?symbols=BTC/USD,ETH/USD")
    assert market.prov.calls == 1


def test_price_empty_when_no_symbols():
    assert _client(FakeMarket()).get("/api/price").json() == {}
