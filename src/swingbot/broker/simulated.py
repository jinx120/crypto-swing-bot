from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from swingbot.exits import exit_decision
from swingbot.journal import Trade
from swingbot.types import ExitReason, Regime, Side


@dataclass
class Position:
    entry_ts: datetime
    entry_price: float
    qty: float
    stop: float
    tp: float
    max_hold_until: datetime
    score_at_entry: float
    regime_at_entry: Regime


class SimulatedBroker:
    """Backtest broker: models long-only bracket fills with fees + slippage.

    Exit priority within a single bar: STOP, then TAKE_PROFIT, then TIME_CAP.
    Stop is checked first as the conservative assumption.
    """

    def __init__(self, cash: float, fee_rate: float = 0.0025, slippage_rate: float = 0.0005):
        self.cash = cash
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.position: Position | None = None

    def open_long(
        self, ts: datetime, price: float, qty: float, stop: float, tp: float,
        max_hold_until: datetime, score_at_entry: float, regime_at_entry: Regime,
    ) -> None:
        if self.position is not None or qty <= 0:
            return
        fill = price * (1 + self.slippage_rate)
        cost = fill * qty
        fee = cost * self.fee_rate
        self.cash -= cost + fee
        self.position = Position(ts, fill, qty, stop, tp, max_hold_until,
                                 score_at_entry, regime_at_entry)

    def update(self, candle: dict) -> Trade | None:
        """Process one bar after entry. Returns a Trade if the position exited."""
        if self.position is None:
            return None
        p = self.position
        decision = exit_decision(
            stop=p.stop, tp=p.tp, max_hold_until=p.max_hold_until,
            high=candle["high"], low=candle["low"], close=candle["close"],
            now=candle["ts"],
        )
        if decision is None:
            return None
        reason, exit_price = decision
        return self._close(candle["ts"], exit_price, reason)

    def force_close(self, ts: datetime, price: float) -> Trade | None:
        if self.position is None:
            return None
        return self._close(ts, price, ExitReason.END_OF_DATA)

    def _close(self, ts: datetime, price: float, reason: ExitReason) -> Trade:
        p = self.position
        fill = price * (1 - self.slippage_rate)
        proceeds = fill * p.qty
        fee = proceeds * self.fee_rate
        self.cash += proceeds - fee

        entry_fee = p.entry_price * p.qty * self.fee_rate
        pnl = (fill - p.entry_price) * p.qty - fee - entry_fee

        trade = Trade(
            entry_ts=p.entry_ts, exit_ts=ts, side=Side.LONG,
            entry_price=p.entry_price, exit_price=fill, qty=p.qty,
            pnl=pnl, exit_reason=reason,
            score_at_entry=p.score_at_entry, regime_at_entry=p.regime_at_entry,
        )
        self.position = None
        return trade

    def equity(self, mark_price: float) -> float:
        pos_value = self.position.qty * mark_price if self.position else 0.0
        return self.cash + pos_value
