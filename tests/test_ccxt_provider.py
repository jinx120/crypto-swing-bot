import pandas as pd

from swingbot.data.ccxt_provider import CcxtProvider


def test_quote_map_translates_usd_to_usdt():
    p = CcxtProvider(exchange_id="binance", exchange=object())
    assert p.map_symbol("BTC/USD") == "BTC/USDT"
    assert p.map_symbol("ETH/USD") == "ETH/USDT"


def test_per_symbol_override_wins_over_quote_map():
    p = CcxtProvider(exchange_id="kraken", exchange=object(),
                     symbol_overrides={"BTC/USD": "XBT/USD"})
    assert p.map_symbol("BTC/USD") == "XBT/USD"


def test_custom_quote_map_passes_unknown_quotes_through():
    p = CcxtProvider(exchange_id="coinbase", exchange=object(), quote_map={})
    assert p.map_symbol("BTC/USD") == "BTC/USD"  # exact USD venue, no remap


class _FakeExchange:
    """Serves OHLCV from an in-memory list, paginating like ccxt:
    fetch_ohlcv returns up to `page` bars at ts >= since. Rows are
    [ts_ms, open, high, low, close, volume]."""

    def __init__(self, rows, page=3):
        self.rows = rows
        self.page = page
        self.calls = []  # (symbol, timeframe, since, limit) for assertions

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.calls.append((symbol, timeframe, since, limit))
        since = since or 0
        out = [r for r in self.rows if r[0] >= since]
        # A real exchange caps the page at its own max size regardless of the
        # requested `limit`, which is what forces the provider to paginate.
        cap = min(limit, self.page) if limit else self.page
        return out[:cap]

    def fetch_ticker(self, symbol):
        return {"last": self.rows[-1][4]}


def _rows(start_ms, n, step_ms=900_000):
    # 900_000 ms = 15m. price climbs so bars are distinguishable.
    return [[start_ms + i * step_ms, 100 + i, 101 + i, 99 + i, 100.5 + i, 10 + i]
            for i in range(n)]


def test_range_paginates_until_end_and_maps_symbol():
    rows = _rows(0, 10)  # ts 0 .. 9*900_000
    ex = _FakeExchange(rows, page=3)
    p = CcxtProvider(exchange_id="binance", exchange=ex)
    df = p.get_candles_range("BTC/USD", "15m", start_ms=0, end_ms=9 * 900_000)
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert len(df) == 10                       # all bars, across multiple pages
    assert len(ex.calls) >= 4                  # 10 bars / 3 per page -> paginated
    assert ex.calls[0][0] == "BTC/USDT"        # symbol was mapped
    assert str(df["ts"].dt.tz) == "UTC"        # canonical UTC Timestamp
    assert df["ts"].is_monotonic_increasing


def test_range_stops_at_end_ms():
    ex = _FakeExchange(_rows(0, 10), page=100)
    p = CcxtProvider(exchange_id="binance", exchange=ex)
    df = p.get_candles_range("BTC/USD", "15m", start_ms=0, end_ms=3 * 900_000)
    assert df["ts"].max() <= pd.Timestamp(3 * 900_000, unit="ms", tz="UTC")


def test_get_candles_range_tail_is_deterministic():
    ex = _FakeExchange(_rows(0, 50), page=1000)
    p = CcxtProvider(exchange_id="binance", exchange=ex)
    df = p.get_candles_range("BTC/USD", "15m", start_ms=0, end_ms=49 * 900_000).tail(5)
    assert len(df) == 5
    assert df["open"].tolist() == [145.0, 146.0, 147.0, 148.0, 149.0]


def test_get_latest_price_uses_ticker():
    ex = _FakeExchange(_rows(0, 3), page=10)
    p = CcxtProvider(exchange_id="binance", exchange=ex)
    assert p.get_latest_price("BTC/USD") == ex.rows[-1][4]
