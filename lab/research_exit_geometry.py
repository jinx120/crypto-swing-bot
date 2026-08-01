"""Exit-geometry walk-forward study.

Every prior crypto-swing-bot study held exit geometry constant at
stop_atr_mult 1.5 / take_profit_atr_mult 3.0 / max_hold_bars 48 and gridded only
signal parameters. This runner inverts that: signal parameters are frozen at the
base profiles' declared defaults and the 18-combo grid varies ONLY the exits.

The baseline combo (1.5 / 3.0 / 48) is a deliberate grid member. If walk-forward
keeps selecting it, that is direct evidence the exit lever is inert - a cleaner
null than "the widened variant lost", because the harness was free to pick either.

Graded against the pre-registered Phase 1 gate in
docs/superpowers/specs/2026-07-31-hold-period-exit-geometry-design.md:
breakeven >= 60 bps, median eligible combos >= 3, end_of_data share <= 15%.
"""
from __future__ import annotations

import os

from lab.research_data import attach_extra, load, resample
from lab.research_ema_4h import base_profile
from lab.research_premium import standalone_profile
from lab.walkforward import (breakeven_cost, phase_gate_verdict,
                             promotion_verdict, walk_forward)
from swingbot.data.series_store import SeriesStore

# Denser around the 60 bps gate than at the extremes: the gate only needs
# breakeven resolved near 60, and 0/10/25/60 are retained so the numbers stay
# directly comparable to the published SIGNAL_RESEARCH_FINDINGS.md tables.
COSTS = [0.0, 0.0010, 0.0025, 0.0050, 0.0055, 0.0060, 0.0065, 0.0070, 0.0080]
GATE_COST = 0.0060

# 18 combinations. The ONLY axis that varies. Baseline is (1.5, 3.0, 48).
EXIT_GRID = [
    {"stop_atr_mult": s, "take_profit_atr_mult": tp, "max_hold_bars": h}
    for s in (1.5, 2.5, 3.5)
    for tp in (3.0, 6.0, 9.0)
    for h in (48, 120)
]

BASELINE_COMBO = {"stop_atr_mult": 1.5, "take_profit_atr_mult": 3.0, "max_hold_bars": 48}

DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", "/tmp/swingbot-bt")


def _configs():
    """(label, symbol, profile_factory, needs_premium) for the 4 configurations."""
    for symbol in ("BTC/USD", "ETH/USD"):
        yield "ema-4h", symbol, base_profile, False
    for symbol in ("BTC/USD", "ETH/USD"):
        yield "premium-standalone", symbol, standalone_profile, True


def main() -> None:
    store = SeriesStore(os.path.join(DATA_DIR, "series.db"))
    # The premium is a BTC-venue spread used as a market-wide US-demand gauge, so
    # the same series is attached to both symbols - the same choice the 2026-07-26
    # study made, kept identical here so the numbers stay comparable.
    premium = store.get_df("cb_premium", "BTC/USD")
    if premium.empty:
        raise SystemExit("no cb_premium series: run `python -m lab.premium_ingest` first")

    for label, symbol, factory, needs_premium in _configs():
        df = resample(load(symbol, "15m"), "4h")
        if needs_premium:
            df = attach_extra(df, "cb_premium", premium)
        print(f"\n=== {label} {symbol} 4h: {len(df)} bars "
              f"{df['ts'].iloc[0]} -> {df['ts'].iloc[-1]} ===", flush=True)

        pf_by_cost: dict[float, float] = {}
        graded = None
        for cost in COSTS:
            result = walk_forward(df, factory(symbol), EXIT_GRID, round_trip=cost,
                                  train_days=365, test_days=90, step_days=90)
            verdict = promotion_verdict(result)
            pf_by_cost[cost] = verdict.profit_factor
            if cost == GATE_COST:
                graded = result
            marker = "  <-- GATE" if cost == GATE_COST else ""
            print(f"  {cost * 10_000:5.0f} bps | windows {len(result.windows):2d} "
                  f"| trades {verdict.n_trades:4d} | net {verdict.net_return_pct:7.2f}% "
                  f"| PF {verdict.profit_factor:5.2f} "
                  f"| +windows {verdict.positive_window_frac:4.0%} "
                  f"| {verdict.decision}{marker}", flush=True)

        breakeven = breakeven_cost(pf_by_cost)
        gate = phase_gate_verdict(graded, breakeven)
        be_txt = f"{breakeven * 10_000:.0f} bps" if breakeven is not None else "none"
        n_baseline = sum(1 for w in graded.windows if w.combo == BASELINE_COMBO)
        print(f"  breakeven: {be_txt}")
        print(f"  median eligible combos/window: {graded.median_eligible_combos:.1f} "
              f"(of {len(EXIT_GRID)})")
        print(f"  exit reasons @ gate: {graded.exit_reason_counts()}")
        print(f"  end_of_data share: {graded.end_of_data_frac:.1%}")
        print(f"  baseline combo selected in {n_baseline}/{len(graded.windows)} windows")
        print("  selected combos: "
              + ", ".join(str(w.combo) for w in graded.windows))
        print(f"  PHASE GATE: {gate.decision} - {gate.reason}", flush=True)


if __name__ == "__main__":
    main()
