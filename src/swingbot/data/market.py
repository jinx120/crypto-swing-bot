from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from swingbot.data.store import CandleStore

_UNIT_SECONDS = {"m": 60, "h": 3600, "d": 86400}


def timeframe_seconds(tf: str) -> int:
    """Bar interval in seconds for a timeframe like '15m', '4h', '1d'."""
    m = re.fullmatch(r"(\d+)([mhd])", tf or "")
    if not m:
        return 900
    return int(m.group(1)) * _UNIT_SECONDS[m.group(2)]


@dataclass(frozen=True)
class ClosedBarFreshness:
    closed: pd.DataFrame
    bar_ts: datetime | None
    fresh: bool


def closed_bars(bars: pd.DataFrame, timeframe: str, now: datetime) -> pd.DataFrame:
    """Return only bars whose full interval has elapsed at the supplied clock."""
    if bars.empty:
        return bars.copy()
    interval = pd.Timedelta(seconds=timeframe_seconds(timeframe))
    timestamps = pd.to_datetime(bars["ts"], utc=True)
    now_ts = pd.Timestamp(now)
    if now_ts.tzinfo is None:
        now_ts = now_ts.tz_localize("UTC")
    else:
        now_ts = now_ts.tz_convert("UTC")
    return bars.loc[timestamps + interval <= now_ts].copy().reset_index(drop=True)


def closed_bar_freshness(
    bars: pd.DataFrame,
    timeframe: str,
    now: datetime,
    provider_grace: int = 120,
) -> ClosedBarFreshness:
    """Return closed bars and whether the latest is within provider grace."""
    closed = closed_bars(bars, timeframe=timeframe, now=now)
    if closed.empty:
        return ClosedBarFreshness(closed=closed, bar_ts=None, fresh=False)
    bar_ts = pd.Timestamp(closed["ts"].iloc[-1]).to_pydatetime()
    fresh_until = bar_ts + timedelta(
        seconds=timeframe_seconds(timeframe) + provider_grace
    )
    return ClosedBarFreshness(closed=closed, bar_ts=bar_ts, fresh=now <= fresh_until)


class MarketData:
    """Serves candles from the CandleStore, fetching + caching from Alpaca on a
    cache miss or when the stored data is stale.

    This lets the chart request ANY timeframe (1m/15m/1h/1d ...) even though the
    background poller only keeps the active strategy's timeframe continuously warm.
    """

    def __init__(self, store: CandleStore, creds, data_source: str = "coinbase",
                 default_lookback: int = 500):
        self.store = store
        self.creds = creds
        self.data_source = data_source
        self.default_lookback = default_lookback

    def _provider(self):
        from swingbot.data.provider_factory import provider_for
        return provider_for(self.data_source, self.creds)

    def refresh(self, symbol: str, timeframe: str, lookback: int | None = None) -> int:
        """Force a live fetch from Alpaca and upsert into the store."""
        prov = self._provider()
        if not prov:
            return 0
        df = prov.get_candles(symbol, timeframe, lookback or self.default_lookback)
        return self.store.upsert_df(symbol, timeframe, df)

    def refresh_many(self, symbols, timeframe: str, lookback: int | None = None) -> int:
        """Batched fetch for many symbols at one timeframe; upsert each into the store."""
        prov = self._provider()
        if not prov:
            return 0
        dfs = prov.get_candles_multi(symbols, timeframe, lookback or self.default_lookback)
        return sum(self.store.upsert_df(sym, timeframe, df) for sym, df in dfs.items())

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
