"""Post-hoc circuit-breaker replay over a research trade record.

`run_backtest_fast` is a pure entry/exit replay: its own docstring records that
it does NOT apply the live-only breakers. Every result to date therefore
describes a strategy with its risk controls switched off - and Phase 1 selected
stops as wide as 3.5x ATR against an UNCHANGED 3% daily loss limit, so the
breakers may bind far harder at the selected geometry than at baseline.

Faithful to `swingbot.risk.RiskManager`:
- a UTC day change resets realized_pnl_today and day_start_equity (`start_day`,
  called every tick),
- `max_consecutive_losses` losing trades in a row trip the kill switch,
- realized loss on the day reaching -daily_loss_limit_pct * day_start_equity
  trips it,
- and NOTHING clears the kill switch automatically. `start_day` resets the
  daily PnL counters but not the switch; only an explicit manual resume does
  (`service.py:106`). A trip is terminal for the remainder of the record.

Three deliberate approximations, stated because they bound the result:
1. Suppressing an entry cannot create trades. A real strategy freed of a blocked
   position might have entered somewhere this record never saw, so the surviving
   record is a LOWER bound on activity, not an exact re-simulation.
2. A multi-day hold realises its pnl on its exit day, which is the day the live
   loop's own tick has already rolled to; the new day therefore opens at the
   pre-trade equity.
3. `cooldown_minutes` (45) is not modelled: it is shorter than one 4h bar, so it
   can never block the following entry at this resolution.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BreakerReport:
    kept: list
    blocked: list
    halted_at: object | None
    halt_reason: str

    @property
    def n_kept(self) -> int:
        return len(self.kept)

    @property
    def n_blocked(self) -> int:
        return len(self.blocked)

    @property
    def blocked_frac(self) -> float:
        total = self.n_kept + self.n_blocked
        return self.n_blocked / total if total else 0.0


def apply_breakers(trades, *, starting_equity: float = 1000.0,
                   daily_loss_limit_pct: float = 0.03,
                   max_consecutive_losses: int = 3) -> BreakerReport:
    """Replay `trades` in entry order under the live kill-switch semantics.

    Returns which trades would have survived, which the breakers would have
    suppressed, and when (and why) the switch tripped.
    """
    kept: list = []
    blocked: list = []
    equity = starting_equity
    day: str | None = None
    day_start_equity = starting_equity
    realized_today = 0.0
    consecutive = 0
    halted_at, halt_reason = None, ""

    for trade in sorted(trades, key=lambda t: t.entry_ts):
        entry_day = trade.entry_ts.strftime("%Y-%m-%d")
        if entry_day != day:
            day, realized_today = entry_day, 0.0
            day_start_equity = equity
        if halted_at is not None:
            blocked.append(trade)
            continue
        kept.append(trade)

        exit_day = trade.exit_ts.strftime("%Y-%m-%d")
        if exit_day != day:
            day, realized_today = exit_day, 0.0
            day_start_equity = equity          # pre-trade: the tick rolled first
        equity += trade.pnl
        realized_today += trade.pnl
        consecutive = consecutive + 1 if trade.pnl < 0 else 0

        # Order matches RiskManager._maybe_trip_kill_switch: streak first.
        if consecutive >= max_consecutive_losses:
            halted_at = trade.exit_ts
            halt_reason = f"{consecutive} consecutive losses"
        elif day_start_equity > 0 and \
                realized_today <= -daily_loss_limit_pct * day_start_equity:
            halted_at = trade.exit_ts
            halt_reason = (f"daily loss {realized_today:.2f} <= limit "
                           f"{-daily_loss_limit_pct * day_start_equity:.2f}")

    return BreakerReport(kept=kept, blocked=blocked,
                         halted_at=halted_at, halt_reason=halt_reason)
