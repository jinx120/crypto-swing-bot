from __future__ import annotations

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetStatus, OrderSide, TimeInForce
from alpaca.trading.requests import GetAssetsRequest, MarketOrderRequest

from swingbot.types import BrokerOrder, OrderSide as NormalizedSide, OrderStatus


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

    def submit_market_buy(
        self, symbol: str, qty: float, client_order_id: str
    ) -> BrokerOrder:
        req = MarketOrderRequest(symbol=normalize_symbol(symbol), qty=qty,
                                 side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
                                 client_order_id=client_order_id)
        order = self._client.submit_order(order_data=req)
        return _serialize_order(order)

    def submit_market_sell(
        self, symbol: str, qty: float, client_order_id: str
    ) -> BrokerOrder:
        req = MarketOrderRequest(symbol=normalize_symbol(symbol), qty=qty,
                                 side=OrderSide.SELL, time_in_force=TimeInForce.GTC,
                                 client_order_id=client_order_id)
        order = self._client.submit_order(order_data=req)
        return _serialize_order(order)

    def get_order(
        self, order_id: str | None = None, client_order_id: str | None = None
    ) -> BrokerOrder | None:
        if (order_id is None) == (client_order_id is None):
            raise ValueError("provide exactly one of order_id or client_order_id")
        try:
            if order_id is not None:
                order = self._client.get_order_by_id(order_id)
            else:
                order = self._client.get_order_by_client_id(client_order_id)
        except APIError as exc:
            if exc.status_code == 404:
                return None
            raise
        return _serialize_order(order)

    def cancel_all(self) -> None:
        self._client.cancel_orders()

    def list_usd_pairs(self) -> list[str]:
        """Tradable crypto */USD pairs, sorted. Network call — cache at call site."""
        req = GetAssetsRequest(asset_class=AssetClass.CRYPTO, status=AssetStatus.ACTIVE)
        assets = self._client.get_all_assets(req)
        return sorted(
            a.symbol for a in assets
            if getattr(a, "tradable", False) and a.symbol.endswith("/USD"))


def _enum_value(value) -> str:
    return str(getattr(value, "value", value))


def _serialize_order(order) -> BrokerOrder:
    status_value = _enum_value(order.status)
    try:
        status = OrderStatus(status_value)
    except ValueError as exc:
        raise ValueError(f"unknown Alpaca order status: {status_value}") from exc
    return BrokerOrder(
        order_id=str(order.id),
        client_order_id=str(order.client_order_id) if order.client_order_id else None,
        symbol=str(order.symbol),
        side=NormalizedSide(_enum_value(order.side)),
        status=status,
        requested_qty=float(order.qty),
        filled_qty=float(order.filled_qty or 0),
        filled_avg_price=(
            float(order.filled_avg_price) if order.filled_avg_price is not None else None
        ),
    )
