import os

import pytest

from swingbot.data.ccxt_provider import CcxtProvider

pytestmark = pytest.mark.skipif(
    os.environ.get("SWINGBOT_LIVE_CCXT") != "1",
    reason="set SWINGBOT_LIVE_CCXT=1 to run live CCXT smoke tests (hits the network)")


def test_live_range_fetch_returns_real_bars():
    p = CcxtProvider(exchange_id="binance")
    # ~2 days of 15m bars ending now; just prove pagination + mapping work live.
    import time
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - 2 * 24 * 60 * 60 * 1000
    df = p.get_candles_range("BTC/USD", "15m", start_ms, end_ms)
    assert len(df) > 100
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
