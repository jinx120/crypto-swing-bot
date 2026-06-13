from __future__ import annotations

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, TimeInForce
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest


def normalize_symbol(symbol: str) -> str:
    """Alpaca crypto trading expects 'BTC/USD' form, uppercased."""
    return symbol.upper()


class AlpacaBroker:
    """Live/paper Alpaca crypto broker. Long-only, market orders (no brackets).

    Exit management (stop/take-profit/time-cap) is handled by the Orchestrator,
    which calls submit_market_sell when an exit fires.
    """

    def __init__(self, key_id: str, secret_key: str, paper: bool = True):
        self._client = TradingClient(key_id, secret_key, paper=paper)

    def get_account(self) -> dict:
        a = self._client.get_account()
        return {"equity": float(a.equity), "cash": float(a.cash),
                "buying_power": float(a.buying_power)}

    def get_position(self, symbol: str) -> dict | None:
        """Return None only when Alpaca confirms that no position exists."""
        try:
            p = self._client.get_open_position(normalize_symbol(symbol))
        except APIError as exc:
            if exc.status_code == 404:
                return None
            raise
        return {"symbol": symbol, "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "market_value": float(p.market_value)}

    def submit_market_buy(self, symbol: str, qty: float) -> str:
        req = MarketOrderRequest(symbol=normalize_symbol(symbol), qty=qty,
                                 side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
        order = self._client.submit_order(order_data=req)
        return str(order.id)

    def submit_market_sell(self, symbol: str, qty: float) -> str:
        req = MarketOrderRequest(symbol=normalize_symbol(symbol), qty=qty,
                                 side=OrderSide.SELL, time_in_force=TimeInForce.GTC)
        order = self._client.submit_order(order_data=req)
        return str(order.id)

    def cancel_all(self) -> None:
        self._client.cancel_orders()

    def list_usd_pairs(self) -> list[str]:
        """Tradable crypto */USD pairs, sorted. Network call — cache at call site."""
        req = GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE)
        assets = self._client.get_all_assets(req)
        return sorted(
            a.symbol for a in assets
            if getattr(a, "tradable", False) and a.symbol.endswith("/USD"))
