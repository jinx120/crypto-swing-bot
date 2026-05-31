from __future__ import annotations

import re
import time

from swingbot.data.alpaca import AlpacaData
from swingbot.data.store import CandleStore

_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}


def timeframe_seconds(tf: str) -> int:
    """Bar interval in seconds for a timeframe like '15m', '4h', '1d'."""
    m = re.fullmatch(r"(\d+)([mhd])", tf or "")
    if not m:
        return 900
    return int(m.group(1)) * _UNIT_SECONDS[m.group(2)]


class MarketData:
    """Serves candles from the CandleStore, fetching + caching from Alpaca on a
    cache miss or when the stored data is stale.

    This lets the chart request ANY timeframe (1m/15m/1h/1d ...) even though the
    background poller only keeps the active strategy's timeframe continuously warm.
    """

    def __init__(self, store: CandleStore, creds, default_lookback: int = 500):
        self.store = store
        self.creds = creds
        self.default_lookback = default_lookback

    def _provider(self) -> AlpacaData | None:
        c = self.creds.get() if self.creds else None
        if not c:
            return None
        return AlpacaData(c.key_id, c.secret_key)

    def refresh(self, symbol: str, timeframe: str, lookback: int | None = None) -> int:
        """Force a live fetch from Alpaca and upsert into the store."""
        prov = self._provider()
        if not prov:
            return 0
        df = prov.get_candles(symbol, timeframe, lookback or self.default_lookback)
        return self.store.upsert_df(symbol, timeframe, df)

    def get(self, symbol: str, timeframe: str, limit: int = 500,
            max_age: int | None = None) -> list[dict]:
        """Return up to `limit` bars (oldest-first). If the store is empty or the
        newest bar is older than `max_age` seconds, fetch+cache first."""
        bars = self.store.get(symbol, timeframe, limit)
        if self._is_stale(bars, max_age):
            try:
                self.refresh(symbol, timeframe, max(limit, self.default_lookback))
                bars = self.store.get(symbol, timeframe, limit)
            except Exception as e:  # never let a data hiccup break the endpoint
                print(f"[market] refresh {symbol} {timeframe}: {e}")
        return bars

    @staticmethod
    def _is_stale(bars: list[dict], max_age: int | None) -> bool:
        if not bars:
            return True
        if max_age is None:
            return False
        return (time.time() - bars[-1]["time"]) > max_age
