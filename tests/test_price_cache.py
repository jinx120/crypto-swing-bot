from swingbot.price_cache import PriceCache


class Clock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def test_collapses_calls_within_ttl():
    clock = Clock()
    calls = []
    def fetch(syms):
        calls.append(tuple(syms)); return {s: 100.0 for s in syms}
    pc = PriceCache(fetch, ttl=2.0, clock=clock)
    pc.get(["BTC/USD"]); pc.get(["BTC/USD"])
    assert len(calls) == 1                       # second call served from cache
    clock.t += 3.0
    pc.get(["BTC/USD"])
    assert len(calls) == 2                       # ttl expired -> refetch


def test_serves_last_value_and_marks_stale_on_error():
    clock = Clock()
    state = {"fail": False}
    def fetch(syms):
        if state["fail"]:
            raise RuntimeError("upstream down")
        return {s: 60810.2 for s in syms}
    pc = PriceCache(fetch, ttl=2.0, clock=clock)
    first = pc.get(["BTC/USD"])
    assert first["BTC/USD"]["price"] == 60810.2 and first["BTC/USD"]["stale"] is False
    state["fail"] = True
    clock.t += 5.0
    out = pc.get(["BTC/USD"])
    assert out["BTC/USD"]["price"] == 60810.2     # last good value retained
    assert out["BTC/USD"]["stale"] is True


def test_unknown_symbol_after_failed_first_fetch_is_null_stale():
    def fetch(syms):
        raise RuntimeError("down")
    pc = PriceCache(fetch, ttl=2.0, clock=Clock())
    out = pc.get(["ETH/USD"])
    assert out["ETH/USD"] == {"price": None, "ts": None, "stale": True}
