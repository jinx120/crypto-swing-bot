"""Walk-forward validation of the 4h EMA trend signal (spec 6a).

Why 4h: the 2026-06-22 study found 15m has no gross edge at all because median
ATR/price (0.29% BTC) is below the 0.6% round trip. Resampling to 4h raises it to
~1.37%, and 4h EMA was the only configuration with a pulse (PF 1.17 BTC gross).
That study was a single in-sample fit, though - this one selects parameters on
training data only and grades on untouched out-of-sample quarters.

The verdict is graded at 60 bps (Alpaca's real round trip). The 0/10/25 bps
columns are diagnostic: they show HOW cost-fragile the edge is, not whether to
deploy it.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_ema_4h
"""
from __future__ import annotations

from lab.research_data import load, resample
from lab.walkforward import promotion_verdict, walk_forward
from swingbot.profile import StrategyProfile
from swingbot.types import Regime

COSTS = [0.0, 0.0010, 0.0025, 0.0060]
GATE_COST = 0.0060

# 27 combinations. Deliberately coarse: a fine grid over 12 training quarters
# would fit noise, and each extra knob costs out-of-sample reliability.
EMA_GRID = [
    {"ema_trend.fast": f, "ema_trend.slow": s, "entry_threshold": t}
    for f in (8, 13, 21)
    for s in (34, 55, 89)
    for t in (0.50, 0.65, 0.80)
]


def base_profile(symbol: str) -> StrategyProfile:
    return StrategyProfile(
        symbol=symbol,
        timeframe="4h",
        kind="research",
        label="ema-4h",
        signals={"ema_trend": {"weight": 1.0, "fast": 21, "slow": 55, "band": 0.001}},
        entry_threshold=0.65,
        regime_ma_period=200,
        allowed_regimes=(Regime.UPTREND, Regime.NEUTRAL),
        atr_period=14,
        bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
        risk_per_trade=0.0075, max_hold_bars=48,
        daily_loss_limit_pct=0.03, max_consecutive_losses=3, cooldown_minutes=45,
    )


def main() -> None:
    for symbol in ("BTC/USD", "ETH/USD"):
        df = resample(load(symbol, "15m"), "4h")
        print(f"\n=== {symbol} 4h: {len(df)} bars "
              f"{df['ts'].iloc[0]} -> {df['ts'].iloc[-1]} ===")
        for cost in COSTS:
            result = walk_forward(df, base_profile(symbol), EMA_GRID,
                                  round_trip=cost, train_days=365,
                                  test_days=90, step_days=90)
            v = promotion_verdict(result)
            tag = "  <-- GATE" if cost == GATE_COST else ""
            print(f"  {int(cost * 1e4):>3} bps | windows {len(result.windows):>2} "
                  f"| trades {v.n_trades:>4} | net {v.net_return_pct:>7.2f}% "
                  f"| PF {v.profit_factor:>5.2f} "
                  f"| +windows {v.positive_window_frac:>5.0%} "
                  f"| {v.decision}{tag}")
            if cost == GATE_COST:
                print(f"        verdict: {v.reason}")
                print("        chosen params per window: "
                      + ", ".join(str(w.combo) for w in result.windows))


if __name__ == "__main__":
    main()
