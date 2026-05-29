from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone

import pandas as pd

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, CryptoLatestTradeRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

_UNITS = {"m": TimeFrameUnit.Minute, "h": TimeFrameUnit.Hour, "d": TimeFrameUnit.Day}
_CANON = ["ts", "open", "high", "low", "close", "volume"]


def parse_timeframe(tf: str) -> TimeFrame:
    m = re.fullmatch(r"(\d+)([mhd])", tf)
    if not m:
        raise ValueError(f"bad timeframe {tf!r}; use like '15m', '4h', '1d'")
    return TimeFrame(int(m.group(1)), _UNITS[m.group(2)])


def fetch_window_days(timeframe: str, lookback: int) -> int:
    """Days to fetch so `lookback` bars at `timeframe` are comfortably covered
    (~3x for warmup + venue gaps), minimum 1 day."""
    m = re.fullmatch(r"(\d+)([mhd])", timeframe)
    if not m:
        raise ValueError(f"bad timeframe {timeframe!r}")
    minutes = int(m.group(1)) * {"m": 1, "h": 60, "d": 1440}[m.group(2)]
    total_minutes = minutes * lookback * 3
    return max(1, math.ceil(total_minutes / (60 * 24)))


def bars_to_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df = df.rename(columns={"timestamp": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df[_CANON].sort_values("ts").reset_index(drop=True)


class AlpacaData:
    """Alpaca crypto market data. Implements the MarketDataProvider protocol."""

    def __init__(self, key_id: str, secret_key: str):
        self._client = CryptoHistoricalDataClient(key_id, secret_key)

    def get_candles(self, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame:
        tf = parse_timeframe(timeframe)
        start = datetime.now(timezone.utc) - timedelta(days=fetch_window_days(timeframe, lookback))
        req = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start)
        bars = self._client.get_crypto_bars(req)
        records = []
        for bar in bars[symbol]:
            records.append({
                "timestamp": bar.timestamp, "open": bar.open, "high": bar.high,
                "low": bar.low, "close": bar.close, "volume": bar.volume,
            })
        df = bars_to_df(records)
        return df.tail(lookback).reset_index(drop=True)

    def get_latest_price(self, symbol: str) -> float:
        req = CryptoLatestTradeRequest(symbol_or_symbols=symbol)
        trade = self._client.get_crypto_latest_trade(req)
        return float(trade[symbol].price)
