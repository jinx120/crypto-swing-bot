"""Phase 2 - deep exit-geometry study over ~11 years of 4h bars.

Phase 1 (docs/HOLD_PERIOD_FINDINGS.md) showed the exit lever is large: breakeven
moved from 18-44 bps to 70-90, and every configuration cleared the 60 bps we pay.
What it could NOT show is whether the edge is CONSISTENT - 14 quarters spanning
one and a half cycles put the positive-window fraction at 36-43% against the 50%
the promotion gate requires, and 14 windows cannot separate "genuinely
inconsistent" from "small sample".

This runner re-runs the IDENTICAL configuration - same frozen signal parameters,
same 18-combo exit grid, same 13-tier cost ladder, same train 365 / test 90 /
step 90 windows, all imported rather than retyped - over Coinbase history from
2015-07-20 (BTC) and 2016-05-18 (ETH). That is roughly 40 and 37 out-of-sample
quarters across three market cycles.

Resolution stays 4h (resampled from the 1h deep backfill) rather than moving to
1d as spec section 6 sketched: at 1d a 365-day training slice holds 365 bars
instead of 2,190, roughly a sixth of the trades, which drops most combos under
the untouchable min_train_trades=20 and starves selection by construction. The
daily arm is a separate question, run by lab/research_exit_geometry_daily.py.

The breaker report is new and may matter more than the headline. Every prior
result ran with the live risk controls switched off; see lab/breakers.py.

Run:
    SWINGBOT_DATA_DIR=/tmp/swingbot-deep .venv/bin/python -m lab.research_exit_geometry_deep
"""
from __future__ import annotations

import pandas as pd

from lab.breakers import apply_breakers
from lab.research_data import load, resample
from lab.research_ema_4h import base_profile
from lab.research_exit_geometry import BASELINE_COMBO, COSTS, EXIT_GRID, GATE_COST
from lab.walkforward import (breakeven_cost, phase_gate_verdict, profit_factor,
                             promotion_verdict, walk_forward)

# The window at which Phase 1's archive begins. Restricting the deep record to it
# reproduces Phase 1's sample, which is how we tell "more history changed the
# answer" apart from "a different venue changed the answer".
PHASE1_START = pd.Timestamp("2022-01-01", tz="UTC")

# Live strategy breaker settings, unchanged from base_profile.
DAILY_LOSS_LIMIT_PCT = 0.03
MAX_CONSECUTIVE_LOSSES = 3


def _breaker_line(label: str, report, total_trades: int) -> str:
    when = report.halted_at.isoformat() if report.halted_at is not None else "never"
    return (f"  breakers[{label}]: kept {report.n_kept}/{total_trades} "
            f"({report.blocked_frac:.0%} blocked) | first halt {when} "
            f"| {report.halt_reason or 'no trip'} "
            f"| PF kept {profit_factor(report.kept):.2f}")


def main() -> None:
    for symbol in ("BTC/USD", "ETH/USD"):
        df = resample(load(symbol, "1h"), "4h")
        print(f"\n=== ema-4h {symbol} 4h deep: {len(df)} bars "
              f"{df['ts'].iloc[0]} -> {df['ts'].iloc[-1]} ===", flush=True)

        pf_by_cost: dict[float, float] = {}
        graded = None
        for cost in COSTS:
            result = walk_forward(df, base_profile(symbol), EXIT_GRID, round_trip=cost,
                                  train_days=365, test_days=90, step_days=90)
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
        n_baseline = sum(1 for w in graded.windows if w.combo == BASELINE_COMBO)

        modern = [w for w in graded.windows if w.window.test_start >= PHASE1_START]
        modern_frac = (sum(1 for w in modern if w.net_pnl > 0) / len(modern)
                       if modern else 0.0)

        print(f"  breakeven: {be_txt}")
        print(f"  median eligible combos/window: {graded.median_eligible_combos:.1f} "
              f"(of {len(EXIT_GRID)})")
        print(f"  exit reasons @ gate: {graded.exit_reason_counts()}")
        print(f"  end_of_data share: {graded.end_of_data_frac:.1%}")
        print(f"  baseline combo selected in {n_baseline}/{len(graded.windows)} windows")
        print(f"  positive windows, full record: {promotion.positive_window_frac:.0%} "
              f"over {len(graded.windows)} windows")
        print(f"  positive windows, 2022+ only: {modern_frac:.0%} over {len(modern)} "
              f"windows (Phase 1 measured 43% over 14)")
        print("  selected combos: " + ", ".join(str(w.combo) for w in graded.windows))

        total = len(graded.oos_trades)
        live = apply_breakers(graded.oos_trades,
                              daily_loss_limit_pct=DAILY_LOSS_LIMIT_PCT,
                              max_consecutive_losses=MAX_CONSECUTIVE_LOSSES)
        daily_only = apply_breakers(graded.oos_trades,
                                    daily_loss_limit_pct=DAILY_LOSS_LIMIT_PCT,
                                    max_consecutive_losses=10 ** 9)
        print(_breaker_line("live 3%/3-streak", live, total))
        print(_breaker_line("daily-loss only", daily_only, total))

        print(f"  PHASE GATE: {gate.decision} - {gate.reason}")
        print(f"  PROMOTION GATE: {promotion.decision} - {promotion.reason}", flush=True)


if __name__ == "__main__":
    main()
