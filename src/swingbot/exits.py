from __future__ import annotations

from datetime import datetime

from swingbot.types import ExitReason


def bracket_levels(
    entry_price: float, atr: float, stop_mult: float, tp_mult: float
) -> tuple[float, float]:
    """Return (stop_price, take_profit_price) for a long position."""
    stop = entry_price - stop_mult * atr
    take_profit = entry_price + tp_mult * atr
    return stop, take_profit


def pct_bracket_levels(entry_price: float, tp_pct: float, sl_pct: float) -> tuple[float, float]:
    """Return (stop_price, take_profit_price) as fixed percentages off entry."""
    stop = entry_price * (1.0 - sl_pct)
    take_profit = entry_price * (1.0 + tp_pct)
    return stop, take_profit


def exit_decision(
    stop: float, tp: float, max_hold_until: datetime | None,
    high: float, low: float, close: float, now: datetime,
) -> tuple[ExitReason, float] | None:
    """Decide whether a long position exits, and a reference exit price.

    Priority: STOP, then TAKE_PROFIT, then TIME_CAP. For live use, pass
    high=low=close=latest_price. The returned price is the modeled fill for
    backtest; live callers submit a market order and use the actual fill.
    """
    if low <= stop:
        return (ExitReason.STOP, stop)
    if high >= tp:
        return (ExitReason.TAKE_PROFIT, tp)
    if max_hold_until is not None and now >= max_hold_until:
        return (ExitReason.TIME_CAP, close)
    return None
