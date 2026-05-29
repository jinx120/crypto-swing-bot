from __future__ import annotations


def position_size(
    equity: float,
    risk_per_trade: float,
    stop_distance: float,
    price: float,
    max_position_frac: float,
) -> float:
    """Fixed-fractional-risk sizing, clamped by a max position fraction.

    stop_distance is in price units (entry - stop). Returns quantity in coin units.
    """
    if stop_distance <= 0 or price <= 0:
        return 0.0
    risk_qty = (equity * risk_per_trade) / stop_distance
    cap_qty = (equity * max_position_frac) / price
    return min(risk_qty, cap_qty)
