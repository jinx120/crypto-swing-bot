from __future__ import annotations

import pandas as pd

from swingbot.data.market import timeframe_seconds

_CANON = ["ts", "open", "high", "low", "close", "volume"]
_DEFAULT_QUOTE_MAP = {"USD": "USDT"}


class CcxtProvider:
    """Market data via CCXT's unified API. Implements MarketDataProvider and
    adds get_candles_range() for deep backfill.

    The app speaks Alpaca symbols (BTC/USD); a config-driven quote_map plus
    optional per-symbol overrides translate to the exchange's symbol (e.g. on
    Binance BTC/USD -> BTC/USDT). Pass `exchange` to inject a client (tests);
    otherwise one is lazily built from `exchange_id`.
    """

    def __init__(self, exchange_id: str = "binance", quote_map: dict | None = None,
                 symbol_overrides: dict | None = None, exchange=None,
                 api_key: str | None = None, secret: str | None = None):
        self.exchange_id = exchange_id
        self.quote_map = _DEFAULT_QUOTE_MAP if quote_map is None else quote_map
        self.symbol_overrides = symbol_overrides or {}
        self._api_key = api_key
        self._secret = secret
        self._exchange = exchange

    def _build_exchange(self):
        import ccxt  # lazy: import only when a real client is needed
        cls = getattr(ccxt, self.exchange_id)
        cfg = {"enableRateLimit": True}
        if self._api_key:
            cfg["apiKey"] = self._api_key
        if self._secret:
            cfg["secret"] = self._secret
        return cls(cfg)

    @property
    def exchange(self):
        if self._exchange is None:
            self._exchange = self._build_exchange()
        return self._exchange

    def map_symbol(self, symbol: str) -> str:
        if symbol in self.symbol_overrides:
            return self.symbol_overrides[symbol]
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            return f"{base}/{self.quote_map.get(quote, quote)}"
        return symbol

    @staticmethod
    def _rows_to_df(rows: list[list]) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(columns=_CANON)
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        return df[_CANON]

    def get_candles_range(self, symbol: str, timeframe: str,
                          start_ms: int, end_ms: int, page_limit: int = 1000) -> pd.DataFrame:
        """Fetch all bars in [start_ms, end_ms], paginating fetch_ohlcv forward.
        CCXT returns <= ~1000 bars/page; we advance `since` past the last bar
        until we reach end_ms or a page returns no progress."""
        ex_symbol = self.map_symbol(symbol)
        step_ms = timeframe_seconds(timeframe) * 1000
        since = start_ms
        collected: list[list] = []
        while since <= end_ms:
            page = self.exchange.fetch_ohlcv(ex_symbol, timeframe, since=since, limit=page_limit)
            if not page:
                break
            for row in page:
                if row[0] > end_ms:
                    break
                collected.append(row)
            last_ts = page[-1][0]
            if last_ts < since:           # exchange returned no forward progress
                break
            since = last_ts + step_ms     # advance past the last bar; an empty next
                                          # page (or since>end_ms) ends the loop
        df = self._rows_to_df(collected)
        if not df.empty:
            df = df.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
        return df

    def get_candles(self, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame:
        """MarketDataProvider impl: most-recent `lookback` bars."""
        step_ms = timeframe_seconds(timeframe) * 1000
        end_ms = self.exchange.milliseconds() if hasattr(self.exchange, "milliseconds") \
            else int(pd.Timestamp.utcnow().timestamp() * 1000)
        start_ms = end_ms - lookback * step_ms * 3  # 3x cushion for venue gaps
        df = self.get_candles_range(symbol, timeframe, start_ms, end_ms)
        return df.tail(lookback).reset_index(drop=True)

    def get_candles_multi(self, symbols, timeframe, lookback):
        return {s: self.get_candles(s, timeframe, lookback) for s in symbols}

    def get_latest_price(self, symbol: str) -> float:
        return float(self.exchange.fetch_ticker(self.map_symbol(symbol))["last"])

    def get_latest_prices(self, symbols):
        return {s: self.get_latest_price(s) for s in symbols}
