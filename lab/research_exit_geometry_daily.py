"""Phase 2 secondary arm - the exit grid at daily resolution.

This is spec section 6's literal daily study, kept because it asks a real
question the 4h study cannot: daily ATR is several times wider than 4h ATR, so a
fixed 60 bps round trip is a much smaller fraction of the move captured. If the
binding constraint really is cost relative to move size, a daily horizon should
amortise it further still.

It is NOT the consistency test. At 1d a 90-day test window carries on the order
of one or two trades, so its per-window statistic is noisier than the 14-window
record Phase 1 produced - which is exactly why the primary study stayed at 4h.

Two adaptations, both pre-registered before the run:

1. Hold levels are rescaled to the CALENDAR equivalents of the 4h grid: 48 bars
   at 4h is 8 days, 120 bars is 20 days. Carrying 48 and 120 over as bar counts
   would mean 48- and 120-DAY holds against a 90-day test window, which would
   force end_of_data truncation past the 15% validity ceiling by construction.
2. `train_days` is selected by `select_train_days` from a probe of ELIGIBILITY
   COUNTS ONLY - how many grid combos clear the untouchable min_train_trades=20.
   No profit factor, net return or window fraction enters the choice, so it
   cannot import hindsight. If no candidate clears the bar the arm reports
   INCONCLUSIVE and does not run: structurally untestable, not negative.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -m lab.research_exit_geometry_daily
"""
from __future__ import annotations

import dataclasses

from lab.breakers import apply_breakers
from lab.research_data import load
from lab.research_ema_4h import base_profile
from lab.research_exit_geometry import COSTS, GATE_COST
from lab.walkforward import (breakeven_cost, phase_gate_verdict, profit_factor,
                             promotion_verdict, walk_forward)

# Same stop/take-profit multiples as Phase 1; holds rescaled to calendar days.
DAILY_EXIT_GRID = [
    {"stop_atr_mult": s, "take_profit_atr_mult": tp, "max_hold_bars": h}
    for s in (1.5, 2.5, 3.5)
    for tp in (3.0, 6.0, 9.0)
    for h in (8, 20)
]

TRAIN_DAYS_CANDIDATES = [365, 730, 1095, 1460]
MIN_MEDIAN_ELIGIBLE = 3


def select_train_days(probe: list[tuple[int, float]], *,
                      min_median_eligible: int = MIN_MEDIAN_ELIGIBLE) -> int | None:
    """Smallest train_days whose median eligible-combo count clears the bar.

    Reads ONLY trade-count eligibility, never P&L, so the choice cannot import
    hindsight. Returns None when nothing clears it - which means the daily study
    is structurally untestable rather than negative.
    """
    for train_days, median_eligible in sorted(probe):
        if median_eligible >= min_median_eligible:
            return train_days
    return None


def daily_profile(symbol: str):
    """Phase 1's frozen signal parameters, relabelled for daily bars.

    Only metadata changes. `_warmup_bars` and the hold cap both read the DATA's
    bar spacing, not `profile.timeframe`, so leaving it at "4h" would change no
    behaviour - but it would stamp "ema-4h" on every daily verdict, which is
    exactly the kind of mislabel that outlives the session that made it.
    """
    return dataclasses.replace(base_profile(symbol), timeframe="1d", label="ema-1d")


def _probe(df, profile) -> list[tuple[int, float]]:
    """Eligibility only: how many combos clear min_train_trades per window."""
    probe: list[tuple[int, float]] = []
    for train_days in TRAIN_DAYS_CANDIDATES:
        result = walk_forward(df, profile, DAILY_EXIT_GRID, round_trip=GATE_COST,
                              train_days=train_days, test_days=90, step_days=90)
        probe.append((train_days, result.median_eligible_combos))
        print(f"  probe train_days={train_days:5d} | windows {len(result.windows):3d} "
              f"| median eligible {result.median_eligible_combos:.1f} "
              f"(of {len(DAILY_EXIT_GRID)})", flush=True)
    return probe


def main() -> None:
    for symbol in ("BTC/USD", "ETH/USD"):
        df = load(symbol, "1d")
        profile = daily_profile(symbol)
        print(f"\n=== ema-1d {symbol}: {len(df)} bars "
              f"{df['ts'].iloc[0]} -> {df['ts'].iloc[-1]} ===", flush=True)

        train_days = select_train_days(_probe(df, profile))
        if train_days is None:
            print(f"  INCONCLUSIVE - no train_days in {TRAIN_DAYS_CANDIDATES} reaches "
                  f"a median of {MIN_MEDIAN_ELIGIBLE} eligible combos per window; "
                  f"the daily arm is structurally untestable at min_train_trades=20",
                  flush=True)
            continue
        print(f"  selected train_days={train_days} (smallest clearing the "
              f"eligibility bar)", flush=True)

        pf_by_cost: dict[float, float] = {}
        graded = None
        for cost in COSTS:
            result = walk_forward(df, profile, DAILY_EXIT_GRID, round_trip=cost,
                                  train_days=train_days, test_days=90, step_days=90)
            verdict = promotion_verdict(result)
            pf_by_cost[cost] = verdict.profit_factor
            if cost == GATE_COST:
                graded = result
            marker = "  <-- GATE" if cost == GATE_COST else ""
            print(f"  {cost * 10_000:5.0f} bps | windows {len(result.windows):3d} "
                  f"| trades {verdict.n_trades:5d} | net {verdict.net_return_pct:7.2f}% "
                  f"| PF {verdict.profit_factor:5.2f} "
                  f"| +windows {verdict.positive_window_frac:4.0%} "
                  f"| {verdict.decision}{marker}", flush=True)

        breakeven = breakeven_cost(pf_by_cost)
        gate = phase_gate_verdict(graded, breakeven)
        promotion = promotion_verdict(graded)
        be_txt = f"{breakeven * 10_000:.0f} bps" if breakeven is not None else "none"
        report = apply_breakers(graded.oos_trades)
        when = report.halted_at.isoformat() if report.halted_at is not None else "never"

        print(f"  breakeven: {be_txt}")
        print(f"  median eligible combos/window: {graded.median_eligible_combos:.1f} "
              f"(of {len(DAILY_EXIT_GRID)})")
        print(f"  exit reasons @ gate: {graded.exit_reason_counts()}")
        print(f"  end_of_data share: {graded.end_of_data_frac:.1%}")
        print("  selected combos: " + ", ".join(str(w.combo) for w in graded.windows))
        print(f"  breakers[live 3%/3-streak]: kept {report.n_kept}/"
              f"{len(graded.oos_trades)} ({report.blocked_frac:.0%} blocked) "
              f"| first halt {when} | {report.halt_reason or 'no trip'} "
              f"| PF kept {profit_factor(report.kept):.2f}")
        print(f"  PHASE GATE: {gate.decision} - {gate.reason}")
        print(f"  PROMOTION GATE: {promotion.decision} - {promotion.reason}", flush=True)


if __name__ == "__main__":
    main()
