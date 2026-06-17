from __future__ import annotations
from datetime import datetime, timedelta
from swingbot.exits import bracket_levels
from core_engine.contracts import Action, Decision, OrderIntent


def build_order_intent(decision: Decision, *, symbol: str, now: datetime,
                       equity: float, entry_price: float, atr: float,
                       risk, profile) -> OrderIntent | None:
    if decision.action is not Action.ENTER_LONG:
        return None

    gate = risk.check_can_enter(symbol, now, open_position_count=0)
    if not gate.approved:
        return None

    stop, tp = bracket_levels(entry_price, atr,
                              profile.stop_atr_mult, profile.take_profit_atr_mult)
    qty = risk.size(equity, entry_price, stop)
    if qty <= 0:
        return None

    max_hold = now + timedelta(minutes=profile.max_hold_bars * 5)
    return OrderIntent(symbol=symbol, qty=qty, entry_price=entry_price,
                       stop=stop, tp=tp, max_hold_until=max_hold,
                       reason=decision.reason)
