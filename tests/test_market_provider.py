# tests/test_market_provider.py
from swingbot.data.market import MarketData


class _Store:
    def get(self, *a, **k): return []


class _Creds:
    def __init__(self, provider): self._p = provider; self.calls = 0
    def make_data(self):
        self.calls += 1
        return self._p


def test_provider_delegates_to_make_data():
    sentinel = object()
    creds = _Creds(sentinel)
    md = MarketData(_Store(), creds)
    assert md._provider() is sentinel
    assert creds.calls == 1


def test_provider_none_when_unconfigured():
    creds = _Creds(None)
    md = MarketData(_Store(), creds)
    assert md._provider() is None


def test_provider_none_when_no_creds():
    md = MarketData(_Store(), None)
    assert md._provider() is None
