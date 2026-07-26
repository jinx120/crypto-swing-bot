"""Walk-forward validation of the Coinbase-premium flow signal (spec 6c substitute).

Spec 6c specified on-chain exchange net flow with a +/-2 std-dev band. That metric
has no free data source, so the same hypothesis is tested through the Coinbase
premium, which proxies US spot demand pressure. The 2-std-dev band from the spec
carries over directly as the signal's `band` parameter.

As with funding, both an overlay (premium as a position filter on the 4h EMA
trend) and a standalone variant are tested.

Run (after lab.premium_ingest):
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_premium
"""
from __future__ import annotations

import os

from lab.research_data import attach_extra, load, resample
from lab.research_ema_4h import COSTS, GATE_COST, base_profile
from lab.walkforward import apply_combo, promotion_verdict, walk_forward
from swingbot.data.series_store import SeriesStore
from swingbot.profile import StrategyProfile
from swingbot.types import Regime

# lookback in 4h bars: 30d, 60d, 90d. band follows spec 6c's +/-2 std dev, with
# 1.5 and 2.5 as sensitivity checks.
PREMIUM_GRID = [
    {"premium_flow.lookback": lb, "premium_flow.band": band, "entry_threshold": t}
    for lb in (180, 360, 540)
    for band in (1.5, 2.0, 2.5)
    for t in (0.50, 0.65)
]


def overlay_profile(symbol: str) -> StrategyProfile:
    profile = apply_combo(base_profile(symbol), {"label": "ema+premium-overlay"})
    profile.signals["ema_trend"]["weight"] = 0.7
    profile.signals["premium_flow"] = {"weight": 0.3, "lookback": 180, "band": 2.0}
    return profile


def standalone_profile(symbol: str) -> StrategyProfile:
    return StrategyProfile(
        symbol=symbol, timeframe="4h", kind="research", label="premium-standalone",
        signals={"premium_flow": {"weight": 1.0, "lookback": 180, "band": 2.0}},
        entry_threshold=0.65, regime_ma_period=200,
        allowed_regimes=(Regime.UPTREND, Regime.NEUTRAL),
        atr_period=14, bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
        risk_per_trade=0.0075, max_hold_bars=48,
        daily_loss_limit_pct=0.03, max_consecutive_losses=3, cooldown_minutes=45,
    )


def main() -> None:
    data_dir = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt")
    store = SeriesStore(os.path.join(data_dir, "series.db"))
    premium = store.get_df("cb_premium", "BTC/USD")
    if premium.empty:
        raise SystemExit("no cb_premium series: run `python -m lab.premium_ingest` first")
    print(f"cb_premium: {len(premium)} rows "
          f"{premium['ts'].iloc[0]} -> {premium['ts'].iloc[-1]}")

    for symbol in ("BTC/USD", "ETH/USD"):
        # The premium is a BTC-venue spread used as a market-wide US-demand gauge,
        # so the same series is attached to both symbols (same choice as funding).
        df = attach_extra(resample(load(symbol, "15m"), "4h"), "cb_premium", premium)
        print(f"\n=== {symbol} 4h: {len(df)} bars from {df['ts'].iloc[0]} ===")
        for label, profile in (("overlay", overlay_profile(symbol)),
                               ("standalone", standalone_profile(symbol))):
            print(f"  -- {label} --")
            for cost in COSTS:
                result = walk_forward(df, profile, PREMIUM_GRID, round_trip=cost,
                                      train_days=365, test_days=90, step_days=90)
                v = promotion_verdict(result)
                tag = "  <-- GATE" if cost == GATE_COST else ""
                print(f"    {int(cost * 1e4):>3} bps | windows {len(result.windows):>2} "
                      f"| trades {v.n_trades:>4} | net {v.net_return_pct:>7.2f}% "
                      f"| PF {v.profit_factor:>5.2f} "
                      f"| +windows {v.positive_window_frac:>5.0%} "
                      f"| {v.decision}{tag}")
                if cost == GATE_COST:
                    print(f"          verdict: {v.reason}")


if __name__ == "__main__":
    main()
