from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class PortfolioRiskState:
    kill_switch_active: bool = False
    kill_switch_reason: str = ""
    day: str = ""                         # "YYYY-MM-DD" (UTC)
    realized_pnl_today: float = 0.0
    day_start_equity: float = 0.0


@dataclass(frozen=True)
class PortfolioSettings:
    max_concurrent: int = 5
    max_total_deployed_frac: float = 0.80
    portfolio_daily_loss_limit_pct: float = 0.08


@dataclass(frozen=True)
class PortfolioDecision:
    approved: bool
    reason: str = ""


class PortfolioRiskManager:
    """Single-writer portfolio-level risk gate across all strategies. No IO."""

    def __init__(self, settings: PortfolioSettings, state: PortfolioRiskState):
        self.settings = settings
        self.state = state

    def start_day(self, now: datetime, equity: float) -> None:
        today = now.strftime("%Y-%m-%d")
        if self.state.day != today:
            self.state.day = today
            self.state.realized_pnl_today = 0.0
            self.state.day_start_equity = equity

    def check_can_enter(self, *, equity: float, open_position_count: int,
                        deployed_value: float, prospective_value: float) -> PortfolioDecision:
        if self.state.kill_switch_active:
            return PortfolioDecision(False, f"portfolio kill switch: {self.state.kill_switch_reason}")
        if open_position_count >= self.settings.max_concurrent:
            return PortfolioDecision(False, "max concurrent positions reached")
        cap = self.settings.max_total_deployed_frac * equity
        if deployed_value + prospective_value > cap:
            return PortfolioDecision(
                False, f"deployed cap: {deployed_value + prospective_value:.2f} > {cap:.2f}")
        return PortfolioDecision(True)

    def on_trade_closed(self, pnl: float, now: datetime) -> None:
        self.state.realized_pnl_today += pnl
        limit = -self.settings.portfolio_daily_loss_limit_pct * self.state.day_start_equity
        if self.state.day_start_equity > 0 and self.state.realized_pnl_today <= limit:
            self.state.kill_switch_active = True
            self.state.kill_switch_reason = (
                f"portfolio daily loss {self.state.realized_pnl_today:.2f} <= {limit:.2f}")
