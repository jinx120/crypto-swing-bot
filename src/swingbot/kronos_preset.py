from __future__ import annotations


def kronos_bracket_profile(symbol: str) -> dict:
    """High-frequency Kronos predict->buy->fixed-bracket strategy.

    Tuned for trade FREQUENCY, not edge: a low entry threshold so almost any
    positive forecast fires, tight fast brackets + short max-hold so positions
    recycle quickly, no post-stop cooldown, and effectively-disabled
    per-strategy circuit breakers so the bot keeps entering instead of halting
    itself after a losing streak. This will trade a lot and is not expected to
    be profitable; raise entry_threshold / widen brackets to make it selective.
    """
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
        # score = forecast_pct_change / 0.0075, so 0.05 fires on a ~0.0375% up-forecast
        "entry_threshold": 0.05,
        "bracket_mode": "pct",
        "tp_pct": 0.006,
        "sl_pct": 0.005,
        "max_hold_bars": 8,           # 2h at 15m: recycle stale positions fast
        "cooldown_minutes": 0,        # re-enter immediately after an exit
        "daily_loss_limit_pct": 0.95,    # effectively no daily-loss auto-halt
        "max_consecutive_losses": 100,   # effectively no losing-streak auto-halt
        "max_concurrent": 1,
    }
