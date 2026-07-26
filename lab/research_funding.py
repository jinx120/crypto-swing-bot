"""Walk-forward validation of funding-rate mean reversion (spec 6b).

Two hypotheses are tested separately, because they fail differently:

  overlay    - funding as a veto on the 4h EMA trend entry. If the edge is real,
               it shows up as the SAME trend trades minus the ones taken into
               crowded longs.
  standalone - funding as the only signal. Long-only, so this is "buy when perps
               are crowded short", with the regime gate still applied.

The bot trades Alpaca SPOT and cannot short, so funding is a timing filter, not a
tradeable instrument (spec 6b note). Data is Hyperliquid hourly funding summed to
8h-equivalents, from 2023-05-12 - shorter than the price history, hence the
270-day training windows.

Run (after lab.funding_ingest):
    SWINGBOT_DATA_DIR=/tmp/swingbot-bt .venv/bin/python -m lab.research_funding
"""
from __future__ import annotations

import os

from lab.research_data import attach_extra, load, resample
from lab.research_ema_4h import COSTS, GATE_COST, base_profile
from lab.walkforward import apply_combo, promotion_verdict, walk_forward
from swingbot.data.series_store import SeriesStore
from swingbot.profile import StrategyProfile
from swingbot.types import Regime

TRAIN_DAYS = 270

FUNDING_GRID = [
    {"funding_mr.high_thresh": hi, "funding_mr.low_thresh": lo, "entry_threshold": t}
    for hi in (0.0003, 0.0005, 0.0010)
    for lo in (-0.0001, -0.0005)
    for t in (0.50, 0.65)
]


def overlay_profile(symbol: str) -> StrategyProfile:
    """4h EMA trend with funding as a weighted veto term."""
    # apply_combo({}) returns a deep-enough copy that mutating the nested signal
    # dicts here cannot leak back into base_profile's literal.
    profile = apply_combo(base_profile(symbol), {"label": "ema+funding-overlay"})
    profile.signals["ema_trend"]["weight"] = 0.7
    profile.signals["funding_mr"] = {
        "weight": 0.3, "high_thresh": 0.0005, "low_thresh": -0.0001}
    return profile


def standalone_profile(symbol: str) -> StrategyProfile:
    return StrategyProfile(
        symbol=symbol, timeframe="4h", kind="research", label="funding-standalone",
        signals={"funding_mr": {"weight": 1.0,
                                "high_thresh": 0.0005, "low_thresh": -0.0001}},
        entry_threshold=0.65, regime_ma_period=200,
        allowed_regimes=(Regime.UPTREND, Regime.NEUTRAL),
        atr_period=14, bracket_mode="atr", stop_atr_mult=1.5, take_profit_atr_mult=3.0,
        risk_per_trade=0.0075, max_hold_bars=48,
        daily_loss_limit_pct=0.03, max_consecutive_losses=3, cooldown_minutes=45,
    )


def main() -> None:
    data_dir = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt")
    store = SeriesStore(os.path.join(data_dir, "series.db"))
    funding = store.get_df("funding_8h", "BTC/USD")
    if funding.empty:
        raise SystemExit("no funding_8h series: run `python -m lab.funding_ingest` first")
    print(f"funding_8h: {len(funding)} rows "
          f"{funding['ts'].iloc[0]} -> {funding['ts'].iloc[-1]}")
    print(f"training windows are {TRAIN_DAYS}d (funding history is shorter than price)")

    for symbol in ("BTC/USD", "ETH/USD"):
        # Funding is a BTC-perp reading used as a market-wide crowding gauge, so
        # the same series is attached to both symbols. Stated here because it is
        # a modelling choice, not an oversight.
        df = attach_extra(resample(load(symbol, "15m"), "4h"), "funding_8h", funding)
        df = df[df["ts"] >= funding["ts"].iloc[0]].reset_index(drop=True)
        print(f"\n=== {symbol} 4h: {len(df)} bars from {df['ts'].iloc[0]} ===")
        for label, profile in (("overlay", overlay_profile(symbol)),
                               ("standalone", standalone_profile(symbol))):
            print(f"  -- {label} --")
            for cost in COSTS:
                result = walk_forward(df, profile, FUNDING_GRID, round_trip=cost,
                                      train_days=TRAIN_DAYS, test_days=90, step_days=90)
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
