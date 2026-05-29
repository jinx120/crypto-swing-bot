from __future__ import annotations

from typing import Protocol

import pandas as pd


class MarketDataProvider(Protocol):
    def get_candles(self, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame: ...
    def get_latest_price(self, symbol: str) -> float: ...
