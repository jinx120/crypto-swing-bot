from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from swingbot.journal import Trade
from swingbot.profile import StrategyProfile
from swingbot.sizing import position_size
from swingbot.types import ExitReason


@dataclass
class RiskState:
    kill_switch_active: bool = False
    kill_switch_reason: str = ""
    day: str = ""                         # "YYYY-MM-DD" (UTC)
    realized_pnl_today: float = 0.0
    consecutive_losses: int = 0
    day_start_equity: float = 0.0
    cooldown_until: dict = field(default_factory=dict)   # symbol -> ISO datetime str


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str = ""


class RiskManager:
    """Pure risk logic operating on a mutable RiskState. No IO."""

    def __init__(self, profile: StrategyProfile, state: RiskState):
        self.profile = profile
        self.state = state

    def start_day(self, now: datetime, equity: float) -> None:
        """Call once per tick; resets daily counters when the UTC date changes."""
        today = now.strftime("%Y-%m-%d")
        if self.state.day != today:
            self.state.day = today
            self.state.realized_pnl_today = 0.0
            self.state.consecutive_losses = 0
            self.state.day_start_equity = equity

    def check_can_enter(self, symbol: str, now: datetime,
                        open_position_count: int) -> RiskDecision:
        if self.state.kill_switch_active:
            return RiskDecision(False, f"kill switch active: {self.state.kill_switch_reason}")
        if open_position_count >= self.profile.max_concurrent:
            return RiskDecision(False, "max concurrent positions reached")
        cd = self.state.cooldown_until.get(symbol)
        if cd is not None and now < datetime.fromisoformat(cd):
            return RiskDecision(False, f"cooldown active until {cd}")
        return RiskDecision(True)

    def size(self, equity: float, entry_price: float, stop_price: float) -> float:
        return position_size(
            equity=equity,
            risk_per_trade=self.profile.risk_per_trade,
            stop_distance=entry_price - stop_price,
            price=entry_price,
            max_position_frac=self.profile.max_position_frac,
        )

    def on_trade_closed(self, trade: Trade, now: datetime) -> None:
        self.state.realized_pnl_today += trade.pnl
        if trade.pnl < 0:
            self.state.consecutive_losses += 1
        else:
            self.state.consecutive_losses = 0

        if trade.exit_reason == ExitReason.STOP:
            until = now + _cooldown_delta(self.profile.cooldown_minutes)
            self.state.cooldown_until[self.profile.symbol] = until.isoformat()

        self._maybe_trip_kill_switch()

    def _maybe_trip_kill_switch(self) -> None:
        if self.state.consecutive_losses >= self.profile.max_consecutive_losses:
            self.state.kill_switch_active = True
            self.state.kill_switch_reason = (
                f"{self.state.consecutive_losses} consecutive losses"
            )
            return
        limit = -self.profile.daily_loss_limit_pct * self.state.day_start_equity
        if self.state.day_start_equity > 0 and self.state.realized_pnl_today <= limit:
            self.state.kill_switch_active = True
            self.state.kill_switch_reason = (
                f"daily loss {self.state.realized_pnl_today:.2f} <= limit {limit:.2f}"
            )


def _cooldown_delta(minutes: int):
    from datetime import timedelta
    return timedelta(minutes=minutes)
