from __future__ import annotations
from datetime import timedelta
from swingbot.exits import bracket_levels
from core_engine.config import LOOP_SECONDS
from core_engine.contracts import EnginePosition, OrderIntent


def _field(order, name: str, default=None):
    if order is None:
        return default
    if isinstance(order, dict):
        return order.get(name, default)
    return getattr(order, name, default)


def _is_filled(order) -> bool:
    status = _field(order, "status", "")
    status_value = getattr(status, "value", status)
    return str(status_value).lower() == "filled"


class Executor:
    def __init__(self, broker):
        self._broker = broker

    def enter(self, intent: OrderIntent, now) -> EnginePosition | None:
        order = self._broker.submit_market_buy(
            intent.symbol,
            intent.qty,
            client_order_id=f"core-entry-{int(now.timestamp())}",
        )
        if not _is_filled(order):
            return None
        fill = float(_field(order, "filled_avg_price", intent.entry_price) or intent.entry_price)
        qty = float(_field(order, "filled_qty", intent.qty) or intent.qty)
        return EnginePosition(symbol=intent.symbol, entry_ts=now, entry_price=fill,
                              qty=qty, stop=intent.stop, tp=intent.tp,
                              max_hold_until=intent.max_hold_until)

    def exit(self, position: EnginePosition, price: float, reason: str) -> float | None:
        order = self._broker.submit_market_sell(
            position.symbol,
            position.qty,
            client_order_id=f"core-exit-{reason}",
        )
        if not _is_filled(order):
            return None
        fill = float(_field(order, "filled_avg_price", price) or price)
        qty = float(_field(order, "filled_qty", position.qty) or position.qty)
        return (fill - position.entry_price) * qty

    def reconcile(
        self,
        position: EnginePosition | None,
        *,
        profile=None,
        atr: float | None = None,
        now=None,
    ) -> EnginePosition | None:
        truth = self._broker.get_position(position.symbol if position else "BTC/USD")
        if truth is None:
            return None
        if position is None:
            if profile is None or atr is None or now is None:
                raise ValueError("profile, atr, and now are required to adopt a position")
            entry_price = float(truth["avg_entry_price"])
            stop, tp = bracket_levels(
                entry_price, atr, profile.stop_atr_mult, profile.take_profit_atr_mult
            )
            return EnginePosition(symbol=truth["symbol"], entry_ts=None,
                                  entry_price=entry_price, qty=float(truth["qty"]),
                                  stop=stop, tp=tp,
                                  max_hold_until=now + timedelta(
                                      seconds=profile.max_hold_bars * LOOP_SECONDS
                                  ))
        return position
