from swingbot.data.poller import CandlePoller


class FakeMarket:
    def __init__(self): self.calls = []
    def refresh_many(self, symbols, timeframe, lookback=None):
        self.calls.append((tuple(sorted(symbols)), timeframe)); return len(symbols)


class FakeProfiles:
    def __init__(self, profs): self._p = profs
    def list_armed(self): return list(self._p)
    def get(self, name): return self._p[name]


def test_start_rolls_back_running_flag_when_thread_spawn_fails(monkeypatch):
    poller = CandlePoller(FakeMarket(), FakeProfiles({}))

    class BoomThread:
        def __init__(self, *a, **k): pass
        def start(self): raise RuntimeError("no thread for you")

    monkeypatch.setattr("swingbot.data.poller.threading.Thread", BoomThread)

    import pytest
    with pytest.raises(RuntimeError, match="no thread for you"):
        poller.start()

    # A failed spawn must leave the poller stoppable/restartable, not wedged.
    assert poller._running is False
    assert poller._thread is None


def test_poll_once_warms_all_armed_grouped_by_timeframe():
    market = FakeMarket()
    profiles = FakeProfiles({
        "btc": {"symbol": "BTC/USD", "timeframe": "15m"},
        "eth": {"symbol": "ETH/USD", "timeframe": "15m"},
        "sol": {"symbol": "SOL/USD", "timeframe": "1h"},
    })
    poller = CandlePoller(market, profiles)
    n = poller.poll_once()
    assert n == 3
    assert (("BTC/USD", "ETH/USD"), "15m") in market.calls
    assert (("SOL/USD",), "1h") in market.calls
