import numpy as np
import pandas as pd
import pytest

from lab.funding_ingest import fetch_funding, ingest as ingest_funding, to_8h_equivalent
from lab.premium_ingest import compute_premium, ingest as ingest_premium
from swingbot.data.series_store import SeriesStore

HOUR_MS = 3_600_000


class FakePerpExchange:
    """Stands in for ccxt.hyperliquid: honours `since`, pages forward."""

    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def fetch_funding_rate_history(self, symbol, since=None, limit=None):
        self.calls.append((symbol, since, limit))
        out = [r for r in self.rows if since is None or r["timestamp"] >= since]
        return out[: (limit or len(out))]


class FakeSpotProvider:
    def __init__(self, df):
        self.df = df

    def get_candles_range(self, symbol, timeframe, start_ms, end_ms):
        return self.df


def _funding_rows(n, start_ms=1_700_000_000_000, rate=0.0001):
    return [{"timestamp": start_ms + i * HOUR_MS, "fundingRate": rate} for i in range(n)]


def test_fetch_funding_pages_forward_until_the_end_timestamp():
    ex = FakePerpExchange(_funding_rows(250))
    start = 1_700_000_000_000
    rows = fetch_funding(ex, "BTC/USDC:USDC", start, start + 249 * HOUR_MS, page_limit=100)
    assert len(rows) == 250
    assert len(ex.calls) >= 3            # paged rather than one giant request
    assert rows[0][0] == start // 1000   # epoch SECONDS in the returned rows
    assert [r[1] for r in rows] == [0.0001] * 250


def test_fetch_funding_stops_at_end_ms():
    ex = FakePerpExchange(_funding_rows(250))
    start = 1_700_000_000_000
    rows = fetch_funding(ex, "BTC/USDC:USDC", start, start + 9 * HOUR_MS, page_limit=100)
    assert len(rows) == 10


def test_fetch_funding_terminates_when_the_venue_stops_advancing():
    ex = FakePerpExchange(_funding_rows(5))   # far fewer rows than requested
    start = 1_700_000_000_000
    rows = fetch_funding(ex, "BTC/USDC:USDC", start, start + 10_000 * HOUR_MS)
    assert len(rows) == 5


def test_to_8h_equivalent_sums_a_trailing_eight_hour_window():
    rows = [(i * 3600, 0.0001) for i in range(10)]
    out = to_8h_equivalent(rows)
    assert len(out) == 3                       # first full window is at index 7
    assert out[0][0] == 7 * 3600
    assert out[0][1] == pytest.approx(0.0008)


def test_ingest_funding_writes_8h_equivalents_under_the_store_symbol(tmp_path):
    store = SeriesStore(str(tmp_path / "s.db"))
    ex = FakePerpExchange(_funding_rows(24))
    start = 1_700_000_000_000
    written = ingest_funding(store, ex, since_ms=start, end_ms=start + 23 * HOUR_MS)
    assert written == 17                       # 24 hourly readings -> 17 full windows
    df = store.get_df("funding_8h", "BTC/USD")
    assert len(df) == 17
    assert df["value"].iloc[0] == pytest.approx(0.0008)


def _ohlc(ts, close):
    return pd.DataFrame({"ts": ts, "open": close, "high": close,
                         "low": close, "close": close, "volume": np.ones(len(close))})


def test_compute_premium_is_the_relative_spread_on_shared_timestamps():
    ts = pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC")
    local = _ohlc(ts, np.array([101.0, 102.0, 103.0]))
    offshore = _ohlc(ts, np.array([100.0, 102.0, 100.0]))
    out = compute_premium(local, offshore)
    assert list(out.columns) == ["ts", "value"]
    assert out["value"].round(6).tolist() == [0.01, 0.0, 0.03]


def test_compute_premium_only_keeps_timestamps_present_in_both_venues():
    local = _ohlc(pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC"),
                  np.array([101.0, 102.0, 103.0]))
    offshore = _ohlc(pd.date_range("2024-01-01 04:00", periods=3, freq="4h", tz="UTC"),
                     np.array([100.0, 100.0, 100.0]))
    out = compute_premium(local, offshore)
    assert len(out) == 2


def test_ingest_premium_resamples_local_15m_and_stores_the_series(tmp_path):
    store = SeriesStore(str(tmp_path / "s.db"))
    ts15 = pd.date_range("2024-01-01", periods=32, freq="15min", tz="UTC")
    local15 = _ohlc(ts15, np.full(32, 101.0))
    ts4h = pd.date_range("2024-01-01", periods=2, freq="4h", tz="UTC")
    offshore = _ohlc(ts4h, np.full(2, 100.0))
    written = ingest_premium(store, local15, FakeSpotProvider(offshore),
                             start_ms=0, end_ms=10**13)
    assert written == 2
    df = store.get_df("cb_premium", "BTC/USD")
    assert df["value"].round(6).tolist() == [0.01, 0.01]
