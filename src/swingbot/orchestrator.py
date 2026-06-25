from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.exits import bracket_levels, exit_decision, pct_bracket_levels
from swingbot.indicators import atr
from swingbot.journal import Trade, TradeJournal
from swingbot.profile import StrategyProfile
from swingbot.regime import RegimeFilter
from swingbot.risk import RiskManager
from swingbot.state import StateStore
from swingbot.types import (
    DecisionCode,
    DecisionResult,
    ExitReason,
    MarketContext,
    OpenPosition,
    OrderSide,
    OrderStatus,
    PendingOrder,
    Regime,
    Side,
)

_FAILED_ORDER_STATUSES = {OrderStatus.REJECTED, OrderStatus.CANCELED, OrderStatus.EXPIRED}


class Orchestrator:
    def __init__(self, profile: StrategyProfile, data, broker, state: StateStore,
                 risk: RiskManager, journal: TradeJournal,
                 portfolio_gate=None, portfolio_on_close=None):
        self.profile = profile
        self.data = data
        self.broker = broker
        self.state = state
        self.risk = risk
        self.journal = journal
        self.engine = ConfluenceEngine(build_signals(profile), profile)
        self.regime = RegimeFilter(profile)
        self.paused = False
        self.halted = False
        self.portfolio_gate = portfolio_gate          # (symbol, value) -> decision with .approved
        self.portfolio_on_close = portfolio_on_close  # (pnl, now) -> None

    def reconcile(
        self, now: datetime, *, adopt_broker_position: bool = True
    ) -> DecisionResult:
        """Broker is source of truth. If broker holds a position we don't have
        recorded, adopt it (with conservative exit levels) so we can manage it."""
        pending = self.state.load_pending_order()
        if pending is not None:
            return self._reconcile_pending(pending, now)

        broker_pos = self.broker.get_position(self.profile.symbol)
        stored = self.state.load_position()
        if broker_pos and stored is None and adopt_broker_position:
            price = float(broker_pos["avg_entry_price"])
            if self.profile.bracket_mode == "pct":
                stop, tp = pct_bracket_levels(price, self.profile.tp_pct, self.profile.sl_pct)
            else:
                stop, tp = bracket_levels(price, price * 0.02,
                                          self.profile.stop_atr_mult,
                                          self.profile.take_profit_atr_mult)
            self.state.save_position(OpenPosition(
                symbol=self.profile.symbol, entry_ts=now, entry_price=price,
                qty=float(broker_pos["qty"]), stop=stop, tp=tp,
                max_hold_until=now + self._max_hold(), score_at_entry=0.0,
                regime_at_entry=Regime.NEUTRAL, side=Side.LONG))
            return DecisionResult(
                DecisionCode.BROKER_POSITION_EXISTS,
                "adopted broker-confirmed position",
            )
        if broker_pos:
            return DecisionResult(DecisionCode.BROKER_POSITION_EXISTS, "broker position confirmed")
        elif stored and not broker_pos:
            self.state.clear_position()
            return DecisionResult(DecisionCode.EXITED, "cleared position after broker confirmed flat")
        return DecisionResult(DecisionCode.MANAGED_NO_EXIT, "broker confirmed flat")

    def tick(
        self,
        now: datetime | None = None,
        sizing_equity: float | None = None,
    ) -> DecisionResult:
        now = now or datetime.now(timezone.utc)
        acct = self.broker.get_account()
        self.risk.start_day(now=now, equity=acct["equity"])
        self.state.save_risk_state(self.risk.state)

        pending = self.state.load_pending_order()
        if pending is not None:
            return self._pending_result(pending)
        pos = self.state.load_position()
        if pos is not None:
            return self._manage_open(pos, now)
        return self._maybe_enter(now, acct["equity"], sizing_equity)

    def _manage_open(self, pos: OpenPosition, now: datetime) -> DecisionResult:
        price = self.data.get_latest_price(self.profile.symbol)
        decision = exit_decision(
            stop=pos.stop, tp=pos.tp, max_hold_until=pos.max_hold_until,
            high=price, low=price, close=price, now=now)
        if decision is None:
            return DecisionResult(
                DecisionCode.MANAGED_NO_EXIT,
                "open position remains inside exit bounds",
                {"price": price},
            )
        reason, _ = decision
        return self._submit_exit(pos, now, reason, price)

    def flatten(self, now: datetime | None = None) -> DecisionResult:
        """Force-close any open position at the latest price (manual control)."""
        now = now or datetime.now(timezone.utc)
        pending = self.state.load_pending_order()
        if pending is not None:
            return self._pending_result(pending)
        pos = self.state.load_position()
        if pos is None:
            return DecisionResult(DecisionCode.MANAGED_NO_EXIT, "no open position to flatten")
        price = self.data.get_latest_price(self.profile.symbol)
        return self._submit_exit(pos, now, ExitReason.END_OF_DATA, price)

    def _maybe_enter(
        self,
        now: datetime,
        equity: float,
        sizing_equity: float | None = None,
    ) -> DecisionResult:
        if self.paused:
            return DecisionResult(DecisionCode.PAUSED, "operator paused new entries")
        if self.halted:
            return DecisionResult(DecisionCode.HALTED, "strategy is halted")
        # Defense against state/broker desync: never open a new position if the
        # broker already holds one (prevents a double-buy after a mid-run hiccup).
        if self.broker.get_position(self.profile.symbol) is not None:
            return DecisionResult(
                DecisionCode.BROKER_POSITION_EXISTS,
                "broker already holds a position",
            )
        gate = self.risk.check_can_enter(self.profile.symbol, now=now,
                                         open_position_count=0)
        if not gate.approved:
            return DecisionResult(DecisionCode.RISK_BLOCKED, gate.reason)
        df = self.data.get_candles(self.profile.symbol, self.profile.timeframe,
                                   lookback=self._lookback())
        benchmark = None
        if any(s == "relative_strength" for s in self.profile.signals):
            benchmark = self.data.get_candles(self.profile.benchmark_symbol,
                                              self.profile.timeframe,
                                              lookback=self._lookback())
        ctx = MarketContext(candles=df, benchmark=benchmark)
        reg = self.regime.evaluate(ctx)
        if not self.regime.permits_entry(reg.regime):
            return DecisionResult(
                DecisionCode.REGIME_BLOCKED,
                f"regime {reg.regime.value} does not permit entry",
                {"regime": reg.regime.value},
            )
        conf = self.engine.evaluate(ctx)
        gate_block = self._check_gates(conf)
        if gate_block is not None:
            return gate_block
        if not conf.passed:
            details = {"score": conf.score, "threshold": conf.threshold}
            kronos = conf.signals.get("kronos_forecast")
            if kronos is not None and kronos.meta.get("error") == "no_forecast":
                details["kronos"] = "unavailable"
            return DecisionResult(
                DecisionCode.SIGNAL_BELOW_THRESHOLD,
                "confluence score below entry threshold",
                details,
            )
        price = float(df["close"].iloc[-1])
        if self.profile.bracket_mode == "pct":
            stop, tp = pct_bracket_levels(price, self.profile.tp_pct, self.profile.sl_pct)
        else:
            a = float(atr(df, self.profile.atr_period).iloc[-1])
            if not (a > 0):
                return DecisionResult(DecisionCode.ATR_INVALID, "ATR is not positive", {"atr": a})
            stop, tp = bracket_levels(price, a, self.profile.stop_atr_mult,
                                      self.profile.take_profit_atr_mult)
        qty = self.risk.size(
            equity=sizing_equity if sizing_equity is not None else equity,
            entry_price=price,
            stop_price=stop,
        )
        if qty <= 0:
            return DecisionResult(DecisionCode.SIZE_ZERO, "risk sizing returned zero")
        if self.portfolio_gate is not None:
            decision = self.portfolio_gate(self.profile.symbol, qty * price)
            if not decision.approved:
                return DecisionResult(DecisionCode.PORTFOLIO_BLOCKED, decision.reason)

        pending = PendingOrder(
            client_order_id=self._client_order_id(),
            broker_order_id=None,
            symbol=self.profile.symbol,
            side=OrderSide.BUY,
            submitted_at=now,
            requested_qty=qty,
            stop=stop, tp=tp, max_hold_until=now + self._max_hold(),
            score_at_entry=conf.score,
            regime_at_entry=reg.regime,
        )
        self.state.save_pending_order(pending)
        try:
            order = self.broker.submit_market_buy(
                self.profile.symbol, qty, pending.client_order_id
            )
        except Exception as exc:  # ambiguous: broker may have accepted the client order ID
            return DecisionResult(
                DecisionCode.ERROR,
                f"buy submission failed: {exc}",
                {"exception_type": type(exc).__name__},
            )
        if order.status in _FAILED_ORDER_STATUSES:
            self.state.clear_pending_order()
            return DecisionResult(
                DecisionCode.ORDER_FAILED,
                f"buy order {order.status.value}",
                {"order_id": order.order_id},
            )
        self.state.save_pending_order(replace(pending, broker_order_id=order.order_id))
        return DecisionResult(
            DecisionCode.ORDER_SUBMITTED,
            "buy order submitted",
            {
                "order_id": order.order_id,
                "client_order_id": pending.client_order_id,
                "entry_price": price,
                "stop": stop,
                "tp": tp,
                "score": conf.score,
            },
        )

    def _check_gates(self, conf) -> DecisionResult | None:
        for name, params in self.profile.signals.items():
            if not params.get("gate", False):
                continue
            min_score = float(params.get("min_score", 0.0))
            sig = conf.signals.get(name)
            score = sig.score if sig is not None else 0.0
            if score < min_score:
                return DecisionResult(
                    DecisionCode.GATE_BLOCKED,
                    f"{name} gate not satisfied",
                    {"signal": name, "score": score, "min_score": min_score},
                )
        return None

    def _reconcile_pending(self, pending: PendingOrder, now: datetime) -> DecisionResult:
        if pending.broker_order_id is not None:
            order = self.broker.get_order(order_id=pending.broker_order_id)
        else:
            order = self.broker.get_order(client_order_id=pending.client_order_id)
        if order is None or order.status in _FAILED_ORDER_STATUSES:
            self.state.clear_pending_order()
            return DecisionResult(
                DecisionCode.ORDER_FAILED,
                "pending order was not found or reached a terminal failure",
                {"client_order_id": pending.client_order_id},
            )
        if pending.broker_order_id is None:
            pending = replace(pending, broker_order_id=order.order_id)
            self.state.save_pending_order(pending)
        if pending.side is OrderSide.BUY:
            if order.status is not OrderStatus.FILLED:
                broker_pos = self.broker.get_position(pending.symbol)
                if broker_pos is None:
                    return self._pending_result(pending)
                return self._promote_filled_buy(pending, order, now, broker_pos=broker_pos)
            return self._promote_filled_buy(pending, order, now)
        if order.status is not OrderStatus.FILLED:
            return self._pending_result(pending)
        return self._complete_filled_sell(pending, order, now)

    def _promote_filled_buy(
        self, pending: PendingOrder, order, now: datetime, *, broker_pos: dict | None = None
    ) -> DecisionResult:
        broker_pos = broker_pos or self.broker.get_position(pending.symbol)
        if broker_pos is None:
            return self._pending_result(pending)
        self.state.save_position(OpenPosition(
            symbol=pending.symbol,
            entry_ts=pending.submitted_at,
            entry_price=float(broker_pos["avg_entry_price"]),
            qty=float(broker_pos["qty"]),
            stop=pending.stop,
            tp=pending.tp,
            max_hold_until=pending.max_hold_until,
            score_at_entry=pending.score_at_entry,
            regime_at_entry=pending.regime_at_entry,
            side=Side.LONG,
            entry_order_id=order.order_id,
        ))
        self.state.clear_pending_order()
        return DecisionResult(
            DecisionCode.ENTERED,
            "buy fill and broker position confirmed",
            {"order_id": order.order_id},
        )

    def _complete_filled_sell(self, pending: PendingOrder, order, now: datetime) -> DecisionResult:
        if self.broker.get_position(pending.symbol) is not None:
            return self._pending_result(pending)
        pos = self.state.load_position()
        if pos is None:
            self.state.clear_pending_order()
            return DecisionResult(DecisionCode.EXITED, "sell fill confirmed flat")
        if order.filled_avg_price is None:
            return DecisionResult(
                DecisionCode.EXIT_SUBMITTED,
                "sell is filled but average fill price is not yet available",
            )
        qty = order.filled_qty or pos.qty
        fill_price = order.filled_avg_price
        trade = Trade(
            entry_ts=pos.entry_ts,
            exit_ts=now,
            side=Side.LONG,
            entry_price=pos.entry_price,
            exit_price=fill_price,
            qty=qty,
            pnl=(fill_price - pos.entry_price) * qty,
            exit_reason=pending.exit_reason or ExitReason.END_OF_DATA,
            score_at_entry=pos.score_at_entry,
            regime_at_entry=pos.regime_at_entry,
        )
        self.journal.record(
            trade,
            symbol=pos.symbol,
            entry_order_id=pos.entry_order_id,
            exit_order_id=order.order_id,
        )
        self.risk.on_trade_closed(trade, now=now)
        self.state.save_risk_state(self.risk.state)
        if self.portfolio_on_close is not None:
            self.portfolio_on_close(trade.pnl, now)
        self.state.clear_position()
        self.state.clear_pending_order()
        return DecisionResult(
            DecisionCode.EXITED,
            "sell fill and broker flat state confirmed",
            {"order_id": order.order_id, "fill_price": fill_price},
        )

    def _submit_exit(
        self, pos: OpenPosition, now: datetime, reason: ExitReason, observed_price: float
    ) -> DecisionResult:
        pending = PendingOrder(
            client_order_id=self._client_order_id(),
            broker_order_id=None,
            symbol=pos.symbol,
            side=OrderSide.SELL,
            submitted_at=now,
            requested_qty=pos.qty,
            stop=pos.stop,
            tp=pos.tp,
            max_hold_until=pos.max_hold_until,
            score_at_entry=pos.score_at_entry,
            regime_at_entry=pos.regime_at_entry,
            exit_reason=reason,
            observed_exit_price=observed_price,
        )
        self.state.save_pending_order(pending)
        try:
            order = self.broker.submit_market_sell(pos.symbol, pos.qty, pending.client_order_id)
        except Exception as exc:  # ambiguous: broker may have accepted the client order ID
            return DecisionResult(
                DecisionCode.ERROR,
                f"sell submission failed: {exc}",
                {"exception_type": type(exc).__name__},
            )
        if order.status in _FAILED_ORDER_STATUSES:
            self.state.clear_pending_order()
            return DecisionResult(
                DecisionCode.ORDER_FAILED,
                f"sell order {order.status.value}",
                {"order_id": order.order_id},
            )
        self.state.save_pending_order(replace(pending, broker_order_id=order.order_id))
        return DecisionResult(
            DecisionCode.EXIT_SUBMITTED,
            "sell order submitted",
            {"order_id": order.order_id, "client_order_id": pending.client_order_id},
        )

    @staticmethod
    def _pending_result(pending: PendingOrder) -> DecisionResult:
        if pending.side is OrderSide.BUY:
            return DecisionResult(
                DecisionCode.ORDER_PENDING,
                "buy order remains pending",
                {"client_order_id": pending.client_order_id},
            )
        return DecisionResult(
            DecisionCode.EXIT_SUBMITTED,
            "sell order remains pending",
            {"client_order_id": pending.client_order_id},
        )

    def _client_order_id(self) -> str:
        symbol = self.profile.symbol.replace("/", "-").lower()
        return f"swingbot-{symbol}-{uuid4().hex}"

    def run(self, max_iterations: int | None = None) -> None:
        self.reconcile(datetime.now(timezone.utc))
        count = 0
        while max_iterations is None or count < max_iterations:
            try:
                self.tick()
            except Exception as e:
                print(f"[orchestrator] tick error: {e}")
            count += 1
            time.sleep(self.profile.poll_seconds)

    def _max_hold(self) -> timedelta:
        minutes = _timeframe_minutes(self.profile.timeframe) * self.profile.max_hold_bars
        return timedelta(minutes=minutes)

    def _lookback(self) -> int:
        needs = [self.profile.regime_ma_period, self.profile.atr_period]
        for params in self.profile.signals.values():
            for k in ("period", "window", "lookback"):
                if k in params:
                    needs.append(params[k])
        return max(needs) + 5


def _timeframe_minutes(tf: str) -> int:
    unit = tf[-1]
    n = int(tf[:-1])
    return n * {"m": 1, "h": 60, "d": 1440}[unit]
