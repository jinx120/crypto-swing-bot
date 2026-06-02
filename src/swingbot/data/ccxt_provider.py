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
