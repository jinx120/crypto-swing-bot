from __future__ import annotations


def bracket_levels(
    entry_price: float, atr: float, stop_mult: float, tp_mult: float
) -> tuple[float, float]:
    """Return (stop_price, take_profit_price) for a long position."""
    stop = entry_price - stop_mult * atr
    take_profit = entry_price + tp_mult * atr
    return stop, take_profit
