from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.exits import bracket_levels, exit_decision
from swingbot.indicators import atr
from swingbot.journal import Trade, TradeJournal
from swingbot.profile import StrategyProfile
from swingbot.regime import RegimeFilter
from swingbot.risk import RiskManager
from swingbot.state import StateStore
from swingbot.types import MarketContext, OpenPosition, Regime, Side


class Orchestrator:
    def __init__(self, profile: StrategyProfile, data, broker, state: StateStore,
                 risk: RiskManager, journal: TradeJournal):
        self.profile = profile
        self.data = data
        self.broker = broker
        self.state = state
        self.risk = risk
        self.journal = journal
        self.engine = ConfluenceEngine(build_signals(profile), profile)
        self.regime = RegimeFilter(profile)
        self.paused = False

    def reconcile(self, now: datetime) -> None:
        """Broker is source of truth. If broker holds a position we don't have
        recorded, adopt it (with conservative exit levels) so we can manage it."""
        broker_pos = self.broker.get_position(self.profile.symbol)
        stored = self.state.load_position()
        if broker_pos and stored is None:
            price = float(broker_pos["avg_entry_price"])
            stop, tp = bracket_levels(price, price * 0.02,
                                      self.profile.stop_atr_mult,
                                      self.profile.take_profit_atr_mult)
            self.state.save_position(OpenPosition(
                symbol=self.profile.symbol, entry_ts=now, entry_price=price,
                qty=float(broker_pos["qty"]), stop=stop, tp=tp,
                max_hold_until=now + self._max_hold(), score_at_entry=0.0,
                regime_at_entry=Regime.NEUTRAL, side=Side.LONG))
        elif stored and not broker_pos:
            self.state.clear_position()

    def tick(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        acct = self.broker.get_account()
        self.risk.start_day(now=now, equity=acct["equity"])
        self.state.save_risk_state(self.risk.state)

        pos = self.state.load_position()
        if pos is not None:
            self._manage_open(pos, now)
        else:
            self._maybe_enter(now, acct["equity"])

    def _manage_open(self, pos: OpenPosition, now: datetime) -> None:
        price = self.data.get_latest_price(self.profile.symbol)
        decision = exit_decision(
            stop=pos.stop, tp=pos.tp, max_hold_until=pos.max_hold_until,
            high=price, low=price, close=price, now=now)
        if decision is None:
            return
        reason, _ = decision
        self.broker.submit_market_sell(self.profile.symbol, pos.qty)
        pnl = (price - pos.entry_price) * pos.qty
        trade = Trade(entry_ts=pos.entry_ts, exit_ts=now, side=Side.LONG,
                      entry_price=pos.entry_price, exit_price=price, qty=pos.qty,
                      pnl=pnl, exit_reason=reason, score_at_entry=pos.score_at_entry,
                      regime_at_entry=pos.regime_at_entry)
        self.journal.record(trade)
        self.risk.on_trade_closed(trade, now=now)
        self.state.clear_position()
        self.state.save_risk_state(self.risk.state)

    def flatten(self, now: datetime | None = None) -> None:
        """Force-close any open position at the latest price (manual control)."""
        now = now or datetime.now(timezone.utc)
        pos = self.state.load_position()
        if pos is None:
            return
        price = self.data.get_latest_price(self.profile.symbol)
        self.broker.submit_market_sell(self.profile.symbol, pos.qty)
        pnl = (price - pos.entry_price) * pos.qty
        from swingbot.types import ExitReason
        trade = Trade(entry_ts=pos.entry_ts, exit_ts=now, side=Side.LONG,
                      entry_price=pos.entry_price, exit_price=price, qty=pos.qty,
                      pnl=pnl, exit_reason=ExitReason.END_OF_DATA,
                      score_at_entry=pos.score_at_entry, regime_at_entry=pos.regime_at_entry)
        self.journal.record(trade)
        self.risk.on_trade_closed(trade, now=now)
        self.state.clear_position()
        self.state.save_risk_state(self.risk.state)

    def _maybe_enter(self, now: datetime, equity: float) -> None:
        if self.paused:
            return
        # Defense against state/broker desync: never open a new position if the
        # broker already holds one (prevents a double-buy after a mid-run hiccup).
        if self.broker.get_position(self.profile.symbol) is not None:
            return
        gate = self.risk.check_can_enter(self.profile.symbol, now=now,
                                         open_position_count=0)
        if not gate.approved:
            return
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
            return
        conf = self.engine.evaluate(ctx)
        if not conf.passed:
            return
        price = float(df["close"].iloc[-1])
        a = float(atr(df, self.profile.atr_period).iloc[-1])
        if not (a > 0):
            return
        stop, tp = bracket_levels(price, a, self.profile.stop_atr_mult,
                                  self.profile.take_profit_atr_mult)
        qty = self.risk.size(equity=equity, entry_price=price, stop_price=stop)
        if qty <= 0:
            return
        self.broker.submit_market_buy(self.profile.symbol, qty)
        self.state.save_position(OpenPosition(
            symbol=self.profile.symbol, entry_ts=now, entry_price=price, qty=qty,
            stop=stop, tp=tp, max_hold_until=now + self._max_hold(),
            score_at_entry=conf.score, regime_at_entry=reg.regime, side=Side.LONG))

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
