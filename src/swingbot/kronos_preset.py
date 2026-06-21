from __future__ import annotations


def kronos_bracket_profile(symbol: str) -> dict:
    """System-owned Balanced 15m Kronos predict->buy->fixed-bracket strategy."""
    return {
        "symbol": symbol,
        "timeframe": "15m",
        "signals": {
            "kronos_forecast": {
                "weight": 1.0,
                "pred_len": 4,
                "threshold_pct": 0.0075,
                "neutral_on_error": False,
            }
        },
        "entry_threshold": 1.0,
        "bracket_mode": "pct",
        "tp_pct": 0.015,
        "sl_pct": 0.01,
        "max_concurrent": 1,
    }
