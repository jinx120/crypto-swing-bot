import pandas as pd

from swingbot.data.backfill import ArchiveConfig, Backfiller
from swingbot.data.store import CandleStore


class _FakeProvider:
    """Serves canonical bars for a symbol/timeframe within [start_ms, end_ms]."""

    def __init__(self, bars_by_symbol):
        self.bars_by_symbol = bars_by_symbol      # {symbol: DataFrame(ts,o,h,l,c,v)}
        self.range_calls = []

    def get_candles_range(self, symbol, timeframe, start_ms, end_ms, page_limit=1000):
        self.range_calls.append((symbol, timeframe, start_ms, end_ms))
        df = self.bars_by_symbol.get(symbol)
        if df is None:
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        # Epoch ms, independent of the column's internal datetime unit
        # (pandas may store ns or us) and of its timezone.
        ms = (df["ts"] - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(milliseconds=1)
        return df[(ms >= start_ms) & (ms <= end_ms)].reset_index(drop=True)


def _bars(start, n):
    ts = pd.date_range(start, periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": range(n), "high": range(n),
                         "low": range(n), "close": range(n), "volume": range(n)})


def test_backfill_writes_bars_into_store(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    prov = _FakeProvider({"BTC/USD": _bars("2024-06-01", 100)})
    cfg = ArchiveConfig(symbols=["BTC/USD"], timeframes=["15m"],
                        history_start="2024-06-01")
    written = Backfiller(store, provider=prov).run(cfg)
    assert written == 100
    assert store.coverage("BTC/USD", "15m")["count"] == 100


def test_backfill_is_idempotent_on_rerun(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    prov = _FakeProvider({"BTC/USD": _bars("2024-06-01", 100)})
    cfg = ArchiveConfig(symbols=["BTC/USD"], timeframes=["15m"],
                        history_start="2024-06-01")
    bf = Backfiller(store, provider=prov)
    bf.run(cfg)
    second = bf.run(cfg)            # re-run over the same window
    assert second == 0             # nothing new written
    assert store.coverage("BTC/USD", "15m")["count"] == 100


def test_backfill_fills_only_the_missing_older_range(tmp_path):
    store = CandleStore(str(tmp_path / "candles.db"))
    full = _bars("2024-06-01", 100)
    # Pre-seed the store with the newest 40 bars only.
    store.upsert_df("BTC/USD", "15m", full.tail(40))
    prov = _FakeProvider({"BTC/USD": full})
    cfg = ArchiveConfig(symbols=["BTC/USD"], timeframes=["15m"],
                        history_start="2024-06-01")
    written = Backfiller(store, provider=prov).run(cfg)
    assert written == 60                       # only the older gap pulled
    assert store.coverage("BTC/USD", "15m")["count"] == 100


def test_config_defaults_are_sensible():
    cfg = ArchiveConfig()
    assert cfg.exchange == "binance"
    assert "BTC/USD" in cfg.symbols
    assert "15m" in cfg.timeframes
    assert cfg.history_start == "2024-06-01"
