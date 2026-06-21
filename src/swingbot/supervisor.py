from __future__ import annotations

import json
import threading
import traceback
from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import uuid4

import pandas as pd


from swingbot.data.market import (
    MarketData,
    closed_bar_freshness,
    closed_bars,
    timeframe_seconds,
)
from swingbot.graduation import can_go_live
from swingbot.journal import TradeJournal
from swingbot.managed_profiles import managed_meta
from swingbot.metrics import compute_metrics
from swingbot.orchestrator import Orchestrator
from swingbot.portfolio_risk import PortfolioDecision, PortfolioRiskManager, PortfolioSettings
from swingbot.profile import StrategyProfile
from swingbot.profiles import ProfileStore
from swingbot.rebalance import Rebalancer, RebalanceSettings, allocated_equity
from swingbot.risk import RiskManager
from swingbot.snapshot import signal_snapshot
from swingbot.state import StateStore, StrategyStateView
from swingbot.telemetry import CycleRecord, TelemetryStore
from swingbot.trade_store import TradeStore
from swingbot.types import DecisionCode, DecisionResult, MarketContext, OrderSide, OrderStatus

class LifecycleError(RuntimeError):
    """An explicit operator lifecycle command (start/stop) did not fully succeed.

    Carries structured attributes so the web layer can report a truthful,
    actionable outcome instead of a bare success. `persist_error` is the
    underlying desire-persistence exception (or None); `stop_timed_out` is True
    when the loop thread was still alive after the join timeout; `rolled_back`
    indicates whether a partially-started loop was successfully stopped again
    (None when not applicable).
    """

    def __init__(self, message: str, *, persist_error: Exception | None = None,
                 stop_timed_out: bool = False, rolled_back: bool | None = None):
        super().__init__(message)
        self.persist_error = persist_error
        self.stop_timed_out = stop_timed_out
        self.rolled_back = rolled_back


class DesirePersistError(LifecycleError):
    """Persisting the durable `running_desired` flag failed during an explicit
    start/stop. Subclass so callers may catch it specifically while still
    matching `LifecycleError`."""


_CANON = ["ts", "open", "high", "low", "close", "volume"]


def _bars_to_df(bars: list[dict]) -> pd.DataFrame:
    """Convert cache bars ({time epoch, o,h,l,c,v}) to the engine's candle DataFrame."""
    if not bars:
        return pd.DataFrame(columns=_CANON)
    df = pd.DataFrame(bars).rename(columns={"time": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], unit="s", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df[_CANON].sort_values("ts").reset_index(drop=True)


class CachedProvider:
    """MarketDataProvider over the candle cache; never calls Alpaca directly.
    Latest prices come from a dict the supervisor refreshes each cycle."""

    def __init__(self, market, latest_prices: dict, timeframes: dict):
        self.market = market
        self.latest = latest_prices          # symbol -> float
        self.timeframes = timeframes          # symbol -> timeframe (price fallback)
        self.cycle_now: datetime | None = None

    def get_candles(self, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame:
        bars = self.market.get(symbol, timeframe, lookback,
                               max_age=timeframe_seconds(timeframe))
        frame = _bars_to_df(bars)
        if self.cycle_now is None:
            return frame
        return closed_bars(frame, timeframe=timeframe, now=self.cycle_now)

    def get_latest_price(self, symbol: str) -> float:
        p = self.latest.get(symbol)
        if p is not None:
            return p
        tf = self.timeframes.get(symbol, "15m")
        bars = self.market.get(symbol, tf, 1, max_age=timeframe_seconds(tf))
        if bars:
            return float(bars[-1]["close"])
        raise RuntimeError(f"no price available for {symbol}")


def _state_locked(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._state_lock:
            return method(self, *args, **kwargs)
    return wrapped


class PortfolioSupervisor:
    """Runs one Orchestrator per armed strategy in a single loop under a shared
    PortfolioRiskManager. The only component that talks to the broker/data upstream.

    Thread safety: lifecycle transitions (start/stop and explicit operator
    request_start/request_stop, plus their desire persistence) are serialized by
    the `_lifecycle_lock` RLock; the mutable trading state shared with the loop
    (StateStore, opened check_same_thread=False with no internal lock, and the
    in-memory PortfolioRiskManager) is protected by the @_state_locked
    `_state_lock` RLock. Lock order is lifecycle then state; never acquire
    lifecycle while holding state.
    """

    def __init__(self, profiles: ProfileStore, creds, state_db: str,
                 market: MarketData | None = None, broker=None, mode: str = "paper",
                 runtime_state=None, reconcile=None):
        self.profiles = profiles
        self.creds = creds
        self.state_db = state_db
        self.market = market
        self.mode = mode
        self.runtime_state = runtime_state    # durable running_desired flag (may be None)
        self._reconcile = reconcile
        self.startup_error: str | None = None  # most recent auto-start outcome
        self._broker = broker
        self.paused = False
        self._running = False
        self._thread: threading.Thread | None = None
        self._latest_prices: dict = {}
        self._timeframes: dict = {}
        self._strategies: dict = {}          # name -> {profile, orch, view, journal, snapshot}
        self._portfolio_risk: PortfolioRiskManager | None = None
        self._rebalance_settings = RebalanceSettings()
        self._rebalance_targets: dict = {}
        self._rebalancer: Rebalancer | None = None
        self._store: StateStore | None = None
        self._telemetry = TelemetryStore(state_db)
        self._trade_store = TradeStore(state_db)
        self._provider: CachedProvider | None = None
        self._summary: dict = {}
        # Lock order: lifecycle -> state. Never acquire lifecycle while holding state.
        self._lifecycle_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._join_timeout = 2.0

    @property
    def running_desired(self) -> bool:
        """Operator wants the loop active across restarts (durable)."""
        return bool(self.runtime_state is not None
                    and self.runtime_state.get_running_desired())

    def mark_desired(self, desired: bool) -> None:
        """Persist desire. No-op when no runtime_state store is wired."""
        if self.runtime_state is not None:
            self.runtime_state.set_running_desired(desired)

    def request_start(self) -> None:
        """Handle an explicit operator Start as one serialized lifecycle operation.

        Start and desire-persistence are atomic under the lifecycle lock. Desire
        is marked only after start() succeeds. If persisting desire fails AND this
        call is what started the loop, roll the loop back so the operator is never
        told Start failed while a live thread keeps trading. A stale startup_error
        is cleared only on full success.
        """
        with self._lifecycle_lock:
            was_running = self._running
            self.start()  # precondition failures (e.g. duplicate thread) propagate as RuntimeError
            try:
                self.mark_desired(True)
            except Exception as persist_err:
                rolled_back: bool | None = None
                if not was_running:
                    rolled_back = self.stop()  # only stop a loop THIS call started
                if rolled_back is True:
                    detail = "loop rolled back"
                elif rolled_back is False:
                    detail = "ROLLBACK STOP TIMED OUT — loop thread still alive"
                else:
                    detail = "loop was already running before this request; left running"
                raise DesirePersistError(
                    f"started loop but failed to persist running_desired=true: "
                    f"{persist_err}; {detail}",
                    persist_error=persist_err,
                    stop_timed_out=(rolled_back is False),
                    rolled_back=rolled_back) from persist_err
            self.startup_error = None

    def request_stop(self) -> None:
        """Handle an explicit operator Stop as one serialized lifecycle operation.

        Desire is cleared first (so a restart cannot auto-resume), but the current
        process is ALWAYS asked to stop even if clearing desire fails — an explicit
        Stop must never leave the loop trading. Persistence and stop failures are
        both surfaced; success raises nothing.
        """
        with self._lifecycle_lock:
            persist_err: Exception | None = None
            try:
                self.mark_desired(False)
            except Exception as e:
                persist_err = e
            stopped = self.stop()  # always attempt, even if desire-clear failed
            problems: list[str] = []
            if persist_err is not None:
                problems.append(
                    "failed to clear running_desired (restart may auto-resume): "
                    f"{persist_err}")
            if not stopped:
                problems.append("stop timed out; loop thread still alive")
            if problems:
                raise LifecycleError(
                    "; ".join(problems),
                    persist_error=persist_err,
                    stop_timed_out=not stopped) from persist_err

    def auto_start_if_desired(self) -> None:
        """Resume a previously desired paper loop on application boot.

        Records `startup_error` instead of raising, so a failed auto-start never
        prevents the web app from serving. Only paper mode auto-resumes; live is
        never started automatically. Does not change `running_desired`. Runs under
        the lifecycle lock so it is ordered against explicit start/stop requests.
        """
        with self._lifecycle_lock:
            self.startup_error = None
            if self.mode != "paper":
                return
            try:
                if not self.running_desired:
                    return
                if not self.profiles.list_armed():
                    self.startup_error = "running desired but no armed strategies to resume"
                    return
                self.start()
            except Exception as e:
                self.startup_error = f"auto-start failed: {e}"

    # ---- construction ----
    @_state_locked
    def build(self) -> None:
        if self._reconcile is not None:
            self._reconcile()
        if self.market is None:
            raise RuntimeError("market must be provided (webmain wires MarketData)")
        if self._broker is None:
            broker = self.creds.make_broker(mode=self.mode) if self.creds else None
            if broker is None:
                raise RuntimeError("Alpaca credentials not set")
            self._broker = broker

        self._store = StateStore(self.state_db)
        # Only the risk-relevant keys belong to PortfolioSettings; other portfolio
        # settings (e.g. default_symbol, a UI concern) are filtered out here.
        _risk_keys = {f.name for f in fields(PortfolioSettings)}
        settings = PortfolioSettings(**{
            k: v for k, v in self.profiles.get_portfolio_settings().items()
            if k in _risk_keys})
        self._portfolio_risk = PortfolioRiskManager(
            settings, self._store.load_portfolio_risk_state())
        self._rebalance_settings = RebalanceSettings(
            **self.profiles.get_rebalance_settings()
        )
        self._rebalance_targets = self.profiles.get_rebalance_targets()
        self._rebalancer = Rebalancer(
            self._rebalance_settings,
            self._store.load_rebalance_state(),
        )

        provider = CachedProvider(self.market, self._latest_prices, self._timeframes)
        self._provider = provider
        self._timeframes.clear()
        self._latest_prices.clear()
        self._strategies = {}
        for name in self.profiles.list_armed():
            pdict = self.profiles.get(name)
            if pdict is None:
                continue
            profile = StrategyProfile.from_dict(pdict)
            self._timeframes[profile.symbol] = profile.timeframe
            view = StrategyStateView(self._store, name)
            risk = RiskManager(profile, view.load_risk_state())
            orch = Orchestrator(
                profile=profile, data=provider, broker=self._broker, state=view,
                risk=risk, journal=TradeJournal(store=self._trade_store, strategy=name),
                portfolio_gate=self._make_gate(name),
                portfolio_on_close=self._make_on_close())
            self._strategies[name] = {"profile": profile, "orch": orch,
                                      "view": view, "snapshot": {}}

    def _strategy_deployed_value(self, name: str) -> float:
        deployed = 0.0
        pos = self._store.load_position(name)
        if pos is not None:
            price = self._latest_prices.get(pos.symbol, pos.entry_price)
            deployed += pos.qty * price
        pending = self._store.load_pending_order(name)
        if pending is not None and pending.side is OrderSide.BUY:
            price = self._latest_prices.get(pending.symbol, 0.0)
            deployed += pending.requested_qty * price
        return deployed

    def _make_gate(self, name: str):
        def gate(symbol: str, prospective_value: float):
            positions = self._store.load_all_positions()
            pending_buys = [
                order for order in self._store.load_all_pending_orders().values()
                if order.side is OrderSide.BUY
            ]
            deployed = 0.0
            for pos in positions.values():
                price = self._latest_prices.get(pos.symbol, pos.entry_price)
                deployed += pos.qty * price
            for order in pending_buys:
                price = self._latest_prices.get(order.symbol, 0.0)
                deployed += order.requested_qty * price
            equity = self._broker.get_account()["equity"]
            decision = self._portfolio_risk.check_can_enter(
                equity=equity, open_position_count=len(positions) + len(pending_buys),
                deployed_value=deployed, prospective_value=prospective_value)
            if not decision.approved:
                return decision
            if self._rebalance_settings.enabled:
                alloc = allocated_equity(
                    name,
                    self._rebalance_targets,
                    equity,
                    len(self._strategies),
                )
                strategy_value = self._strategy_deployed_value(name)
                if strategy_value + prospective_value > alloc:
                    return PortfolioDecision(
                        False,
                        "rebalance soft cap: "
                        f"{strategy_value + prospective_value:.2f} > allocated {alloc:.2f}",
                    )
            return decision
        return gate

    def _make_on_close(self):
        def on_close(pnl: float, now: datetime):
            self._portfolio_risk.on_trade_closed(pnl, now)
            self._store.save_portfolio_risk_state(self._portfolio_risk.state)
        return on_close

    def _symbol_owned_by_other_strategy(self, name: str, symbol: str) -> bool:
        positions = self._store.load_all_positions()
        for strategy, pos in positions.items():
            if strategy != name and pos.symbol == symbol:
                return True
        pending = self._store.load_all_pending_orders()
        for strategy, order in pending.items():
            if strategy != name and order.side is OrderSide.BUY and order.symbol == symbol:
                return True
        return False

    # ---- the loop ----
    @_state_locked
    def tick_all(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if self._provider is not None:
            self._provider.cycle_now = now
        ingest = self._warm(now)
        # The account fetch is a broker round-trip. If it fails (expired creds /
        # network loss) the whole broker is unreachable for this cycle: degrade
        # truthfully instead of letting the exception escape tick_all. We skip the
        # daily-counter reset (never fabricate equity), force every strategy's cycle
        # to a failed-broker outcome below (no entries, positions preserved), and
        # keep the last-known-good summary.
        acct = None
        broker_error: Exception | None = None
        try:
            acct = self._broker.get_account()
            self._portfolio_risk.start_day(now, acct["equity"])
        except Exception as exc:
            broker_error = exc
            print(f"[supervisor] account fetch failed; cycle degraded: {exc}")
        for name in sorted(self._strategies):                 # deterministic priority
            s = self._strategies[name]
            orch = s["orch"]
            orch.paused = bool(self.paused)
            orch.halted = bool(self._portfolio_risk.state.kill_switch_active)
            cycle_id = uuid4().hex
            stages = {
                "ingest": ingest[name]["outcome"],
                "reconcile": "ok",
                "manage": "skipped",
                "decide": "skipped",
                "persist": "ok",
            }
            decision = DecisionResult(DecisionCode.ERROR, "cycle did not complete")
            reconcile_ok = True
            if broker_error is not None:
                # Broker unreachable this cycle: do not touch it (a failed lookup
                # must never be read as "position closed"), record a failed cycle.
                reconcile_ok = False
                stages["reconcile"] = "failed"
                decision = self._error_decision("account", broker_error)
            else:
                try:
                    orch.reconcile(
                        now,
                        adopt_broker_position=not self._symbol_owned_by_other_strategy(
                            name, s["profile"].symbol
                        ),
                    )
                except Exception as exc:
                    reconcile_ok = False
                    stages["reconcile"] = "failed"
                    decision = self._error_decision("reconcile", exc)

            position_exists = s["view"].load_position() is not None
            required_stage = "manage" if position_exists else "decide"
            if not reconcile_ok or stages["ingest"] == "failed":
                stages[required_stage] = "failed"
                if stages["ingest"] == "failed":
                    decision = DecisionResult(
                        DecisionCode.ERROR,
                        ingest[name]["error"] or "fresh closed-bar ingest failed",
                        {"stage": "ingest"},
                    )
            else:
                try:
                    if self._rebalance_settings.enabled and acct is not None:
                        sizing_equity = allocated_equity(
                            name,
                            self._rebalance_targets,
                            acct["equity"],
                            len(self._strategies),
                        )
                        decision = orch.tick(now=now, sizing_equity=sizing_equity)
                    else:
                        decision = orch.tick(now)
                    if not isinstance(decision, DecisionResult):
                        raise TypeError("orchestrator tick returned no DecisionResult")
                    stages[required_stage] = "ok"
                except Exception as exc:
                    stages[required_stage] = "failed"
                    decision = self._error_decision(required_stage, exc)

            try:
                self._store.save_portfolio_risk_state(self._portfolio_risk.state)
            except Exception as exc:
                stages["persist"] = "failed"
                decision = self._error_decision("persist", exc)

            self._telemetry.record(CycleRecord(
                cycle_id=cycle_id,
                strategy=name,
                started_at=now,
                completed_at=now,
                bar_ts=ingest[name]["bar_ts"],
                ingest=stages["ingest"],
                reconcile=stages["reconcile"],
                manage=stages["manage"],
                decide=stages["decide"],
                persist=stages["persist"],
                decision_code=decision.code,
                decision_reason=decision.reason,
                decision_details=decision.details,
            ))
            s["snapshot"] = self._snapshot(s["profile"])
        if acct is not None and self._rebalance_settings.enabled:
            self._run_rebalance(now, acct)
        if acct is not None:
            self._summary = self._build_summary(acct)

    def _run_rebalance(self, now: datetime, acct: dict):
        if self._portfolio_risk.state.kill_switch_active:
            self._telemetry.record_rebalance(
                ts=now.isoformat(),
                mode=self._rebalance_settings.mode,
                ran=False,
                skipped_reason=(
                    "portfolio kill switch: "
                    f"{self._portfolio_risk.state.kill_switch_reason}"
                ),
                allocations_json="[]",
                trims_json="[]",
            )
            return None

        deployed: dict[str, float] = {}
        symbols: dict[str, str] = {}
        prices: dict[str, float] = {}
        returns: dict[str, pd.Series] = {}
        for name in sorted(self._strategies):
            if self._strategy_kill_active(name):
                continue
            profile = self._strategies[name]["profile"]
            deployed[name] = self._strategy_deployed_value(name)
            symbols[name] = profile.symbol
            prices[profile.symbol] = self._price_for(profile.symbol, profile.timeframe)
            returns[profile.symbol] = self._recent_returns(
                profile.symbol,
                profile.timeframe,
                self._rebalance_settings.vol_lookback,
            )

        res = self._rebalancer.evaluate(
            now=now,
            total_equity=acct["equity"],
            deployed=deployed,
            symbols=symbols,
            targets=self._rebalance_targets,
            prices=prices,
            returns_by_symbol=returns,
        )
        if res.ran and res.mode == "hard":
            for trim in res.trims:
                order = self._broker.submit_market_sell(
                    trim.symbol,
                    trim.qty,
                    f"rebalance-{trim.symbol.replace('/', '-').lower()}-{uuid4().hex}",
                )
                if order.status not in {OrderStatus.REJECTED, OrderStatus.CANCELED, OrderStatus.EXPIRED}:
                    self._reduce_stored_position(trim.name, trim.qty)
            self._rebalancer.mark_ran(now)
            self._store.save_rebalance_state(self._rebalancer.state)

        self._telemetry.record_rebalance(
            ts=now.isoformat(),
            mode=res.mode,
            ran=res.ran,
            skipped_reason=res.skipped_reason,
            allocations_json=json.dumps([asdict(a) for a in res.allocations]),
            trims_json=json.dumps([asdict(t) for t in res.trims]),
        )
        return res

    def _strategy_kill_active(self, name: str) -> bool:
        return bool(self._strategies[name]["orch"].risk.state.kill_switch_active)

    def _price_for(self, symbol: str, timeframe: str) -> float:
        price = self._latest_prices.get(symbol)
        if price is not None:
            return float(price)
        if self._provider is not None:
            return float(self._provider.get_latest_price(symbol))
        bars = self.market.get(symbol, timeframe, 1, max_age=None)
        if not bars:
            return 0.0
        return float(bars[-1]["close"])

    def _recent_returns(self, symbol: str, timeframe: str, lookback: int) -> pd.Series:
        try:
            bars = self.market.get(symbol, timeframe, lookback + 1, max_age=None)
        except Exception:
            return pd.Series(dtype=float)
        if not bars:
            return pd.Series(dtype=float)
        return pd.Series([float(bar["close"]) for bar in bars], dtype=float)

    def _reduce_stored_position(self, name: str, qty: float) -> None:
        pos = self._store.load_position(name)
        if pos is None:
            return
        remaining = pos.qty - qty
        if remaining <= 1e-12:
            self._store.clear_position(name)
            return
        self._store.save_position(replace(pos, qty=remaining), name)

    def _warm(self, now: datetime) -> dict[str, dict]:
        by_tf: dict = {}
        for s in self._strategies.values():
            by_tf.setdefault(s["profile"].timeframe, set()).add(s["profile"].symbol)
        refresh_errors: dict[str, str] = {}
        for tf, syms in by_tf.items():
            try:
                self.market.refresh_many(sorted(syms), tf)
            except Exception as e:
                refresh_errors[tf] = f"warm {tf} failed: {e}"
                print(f"[supervisor] warm {tf} error: {e}")
        prov = self.market._provider()
        all_syms = sorted({s["profile"].symbol for s in self._strategies.values()})
        if prov is not None and all_syms and hasattr(prov, "get_latest_prices"):
            try:
                self._latest_prices.update(prov.get_latest_prices(all_syms))
            except Exception as e:
                print(f"[supervisor] latest-price error: {e}")
        results = {}
        for name, strategy in self._strategies.items():
            profile = strategy["profile"]
            error = refresh_errors.get(profile.timeframe)
            try:
                bars = self.market.get(
                    profile.symbol,
                    profile.timeframe,
                    profile.regime_ma_period + 5,
                    max_age=None,
                )
                freshness = closed_bar_freshness(
                    _bars_to_df(bars),
                    timeframe=profile.timeframe,
                    now=now,
                )
                if error is None and not freshness.fresh:
                    error = "no fresh closed bar available"
                results[name] = {
                    "outcome": "failed" if error else "ok",
                    "bar_ts": freshness.bar_ts,
                    "fresh": freshness.fresh,
                    "error": error,
                }
            except Exception as exc:
                results[name] = {
                    "outcome": "failed",
                    "bar_ts": None,
                    "fresh": False,
                    "error": f"ingest failed: {exc}",
                }
        return results

    @staticmethod
    def _error_decision(stage: str, exc: Exception) -> DecisionResult:
        return DecisionResult(
            DecisionCode.ERROR,
            f"{stage} failed: {exc}",
            {"stage": stage, "exception_type": type(exc).__name__},
        )

    def _snapshot(self, profile: StrategyProfile) -> dict:
        try:
            cdf = _bars_to_df(self.market.get(
                profile.symbol, profile.timeframe, profile.regime_ma_period + 5,
                max_age=timeframe_seconds(profile.timeframe)))
            bench = None
            if "relative_strength" in profile.signals:
                bench = _bars_to_df(self.market.get(
                    profile.benchmark_symbol, profile.timeframe, profile.regime_ma_period + 5,
                    max_age=timeframe_seconds(profile.timeframe)))
            return signal_snapshot(profile, MarketContext(candles=cdf, benchmark=bench))
        except Exception as e:
            return {"error": str(e)}

    def _build_summary(self, acct: dict) -> dict:
        positions = self._store.load_all_positions()
        deployed = 0.0
        for pos in positions.values():
            price = self._latest_prices.get(pos.symbol, pos.entry_price)
            deployed += pos.qty * price
        prs = self._portfolio_risk.state
        equity = acct["equity"]
        return {
            "mode": self.mode, "running": self._running, "paused": self.paused,
            "equity": equity, "deployed": deployed,
            "deployed_frac": (deployed / equity) if equity else 0.0,
            "open_positions": len(positions), "day_pnl": prs.realized_pnl_today,
            "kill_switch": {"active": prs.kill_switch_active, "reason": prs.kill_switch_reason},
        }

    @_state_locked
    def rebalance_status(self) -> dict:
        last = self._telemetry.recent_rebalance(1)
        last_state = self._rebalancer.state if self._rebalancer is not None else None
        last_rebalance_at = last_state.last_rebalance_at if last_state is not None else ""
        next_eligible_at = ""
        if last_rebalance_at:
            next_eligible_at = (
                datetime.fromisoformat(last_rebalance_at)
                + timedelta(minutes=self._rebalance_settings.min_interval_minutes)
            ).isoformat()
        allocations = []
        try:
            acct = self._broker.get_account()
            deployed = {
                name: self._strategy_deployed_value(name)
                for name in sorted(self._strategies)
            }
            symbols = {
                name: strategy["profile"].symbol
                for name, strategy in self._strategies.items()
            }
            if self._rebalancer is not None:
                allocations = [
                    asdict(a)
                    for a in self._rebalancer.evaluate(
                        now=datetime.now(timezone.utc),
                        total_equity=acct["equity"],
                        deployed=deployed,
                        symbols=symbols,
                        targets=self._rebalance_targets,
                        prices={},
                        returns_by_symbol={},
                    ).allocations
                ]
        except Exception:
            allocations = []
        return {
            "enabled": self._rebalance_settings.enabled,
            "mode": self._rebalance_settings.mode,
            "allocations": allocations,
            "last_rebalance_at": last_rebalance_at,
            "next_eligible_at": next_eligible_at,
            "last_skip_reason": last[0]["skipped_reason"] if last else "",
        }

    @_state_locked
    def run_rebalance_now(self) -> dict:
        if self._broker is None:
            raise RuntimeError("broker is not configured")
        res = self._run_rebalance(datetime.now(timezone.utc), self._broker.get_account())
        if res is None:
            return self.rebalance_status()
        return {
            "ran": res.ran,
            "skipped_reason": res.skipped_reason,
            "allocations": [asdict(a) for a in res.allocations],
            "trims": [asdict(t) for t in res.trims],
            "mode": res.mode,
        }

    # ---- status + control surface (consumed by Phase 2 web layer) ----
    def _mark(self, symbol: str, timeframe: str):
        """Latest local-market close and bar timestamp for marking a position."""
        if self.market is None:
            return None, None
        try:
            bars = self.market.get(symbol, timeframe, 1)
            if not bars:
                return None, None
            last = bars[-1]
            ts = last.get("time")
            ts_iso = (
                datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
                if isinstance(ts, (int, float)) else None
            )
            return float(last["close"]), ts_iso
        except Exception:
            return None, None

    @_state_locked
    def status(self) -> dict:
        strategies = []
        if self._strategies:
            for name in sorted(self._strategies):
                s = self._strategies[name]
                pos = s["view"].load_position()
                pos_dict = _pos_dict(pos)
                if pos_dict is not None:
                    timeframe = getattr(s["profile"], "timeframe", "15m")
                    mark_price, mark_ts = self._mark(pos.symbol, timeframe)
                    pos_dict["mark_price"] = mark_price
                    pos_dict["mark_ts"] = mark_ts
                    pos_dict["unrealized"] = (
                        (mark_price - pos.entry_price) * pos.qty
                        if mark_price is not None else None
                    )
                rs = s["orch"].risk.state
                meta = managed_meta(name)
                strategies.append({
                    "name": name, "symbol": s["profile"].symbol,
                    "running": self._running,
                    "live_eligible": self.profiles.is_live_eligible(name),
                    "kind": meta["kind"], "label": meta["label"],
                    "snapshot": s["snapshot"],
                    "position": pos_dict,
                    "risk": {"kill_switch": {"active": rs.kill_switch_active,
                                             "reason": rs.kill_switch_reason},
                             "consecutive_losses": rs.consecutive_losses},
                })
        else:
            # Bot not running — populate from DB so dashboard shows armed strategies
            for f in self.profiles.armed_with_flags():
                name = f["name"]
                pdict = self.profiles.get(name)
                symbol = (pdict or {}).get("symbol", "")
                meta = managed_meta(name)
                strategies.append({
                    "name": name, "symbol": symbol,
                    "running": False,
                    "live_eligible": f["live_eligible"],
                    "kind": meta["kind"], "label": meta["label"],
                    "snapshot": {}, "position": None, "risk": None,
                })
        pending = []
        if self._store is not None:
            try:
                for strategy, order in self._store.load_all_pending_orders().items():
                    pending.append(_pending_dict(strategy, order))
            except Exception:
                pending = []
        return {"portfolio": self._summary or {"mode": self.mode, "running": self._running},
                "strategies": strategies, "pending_orders": pending}

    def lifecycle_state(self) -> dict:
        with self._lifecycle_lock:
            thread_alive = bool(self._thread is not None and self._thread.is_alive())
            running_flag = bool(self._running)
            try:
                running_desired: bool | None = self.running_desired
                running_desired_error: str | None = None
            except Exception as e:
                # An unreadable store must not break the lifecycle endpoint, and
                # unreadable desire is reported as null (not a silent false).
                running_desired = None
                running_desired_error = str(e)
            with self._state_lock:
                halted = bool(
                    self._portfolio_risk
                    and self._portfolio_risk.state.kill_switch_active)
                return {
                    "mode": self.mode,
                    "running_flag": running_flag,
                    "thread_alive": thread_alive,
                    "running_actual": thread_alive,
                    "running_desired": running_desired,
                    "running_desired_error": running_desired_error,
                    "paused": bool(self.paused),
                    "halted": halted,
                    "startup_error": self.startup_error,
                }

    def readiness(self) -> dict:
        """Local readiness snapshot; never performs a broker or market network call."""
        lifecycle = self.lifecycle_state()
        with self._state_lock:
            try:
                credentials_ok = bool(self.creds is not None and self.creds.get() is not None)
                credentials_detail = "credentials available" if credentials_ok else "missing credentials"
            except Exception as exc:
                credentials_ok = False
                credentials_detail = f"credentials unreadable: {exc}"
            armed = self.profiles.list_armed()
            recent = self._telemetry.recent(limit=200)
            latest_by_strategy = {}
            for row in recent:
                latest_by_strategy.setdefault(row.strategy, row)
            critical_ok = all(
                row.ingest == "ok" and row.reconcile == "ok" and row.persist == "ok"
                for row in latest_by_strategy.values()
            )
            desired = lifecycle["running_desired"]
            checks = {
                "credentials": {
                    "ok": credentials_ok,
                    "detail": credentials_detail,
                },
                "armed_strategies": {
                    "ok": bool(armed),
                    "detail": f"{len(armed)} armed strategies",
                },
                "lifecycle_desire_readable": {
                    "ok": desired is not None,
                    "detail": lifecycle.get("running_desired_error") or "desire readable",
                },
                "completed_cycle_while_desired": {
                    "ok": desired is not True or bool(recent),
                    "detail": (
                        "completed cycle available"
                        if recent else "no completed cycle available"
                    ),
                },
                "latest_critical_stages": {
                    "ok": critical_ok,
                    "detail": (
                        "latest critical stages succeeded"
                        if critical_ok else "latest critical-stage failure present"
                    ),
                },
            }
            return {"ready": all(check["ok"] for check in checks.values()), "checks": checks}

    def trading_health(self) -> dict:
        """Trading lifecycle and reliability snapshot with no broker mutations/queries."""
        lifecycle = self.lifecycle_state()
        with self._state_lock:
            rows = self._telemetry.recent(limit=200)
            reliability = self._telemetry.reliability(limit=200)
            last_decisions = {}
            for row in rows:
                last_decisions.setdefault(row.strategy, _cycle_dict(row))
            desired = lifecycle["running_desired"]
            actual = lifecycle["running_actual"]
            if desired is False:
                status = "inactive"
            elif desired is None or not actual:
                status = "unhealthy"
            else:
                status = "active"
            return {
                "status": status,
                "lifecycle": lifecycle,
                "last_cycle": _cycle_dict(rows[0]) if rows else None,
                "last_decisions_by_strategy": last_decisions,
                "reliability": reliability,
            }

    # ---- aggregate journal + metrics ----
    def _trades(self, strategy: str | None = None) -> list:
        return self._trade_store.list(strategy=strategy)

    @_state_locked
    def journal(self, strategy: str | None = None) -> list[dict]:
        return [_trade_dict(t) for t in self._trades(strategy)]

    @_state_locked
    def metrics(self, strategy: str | None = None) -> dict:
        return asdict(compute_metrics(self._trades(strategy)))

    # ---- controls ----
    @_state_locked
    def halt(self) -> None:
        if not self._portfolio_risk or not self._store:
            return
        self._portfolio_risk.state.kill_switch_active = True
        self._portfolio_risk.state.kill_switch_reason = "manual halt"
        self._store.save_portfolio_risk_state(self._portfolio_risk.state)
        if "kill_switch" in self._summary:
            self._summary["kill_switch"]["active"] = True
            self._summary["kill_switch"]["reason"] = "manual halt"

    @_state_locked
    def reset(self) -> None:
        if not self._portfolio_risk or not self._store:
            return
        self._portfolio_risk.state.kill_switch_active = False
        self._portfolio_risk.state.kill_switch_reason = ""
        self._store.save_portfolio_risk_state(self._portfolio_risk.state)
        if "kill_switch" in self._summary:
            self._summary["kill_switch"]["active"] = False
            self._summary["kill_switch"]["reason"] = ""

    @_state_locked
    def flatten(self, name: str | None = None) -> None:
        targets = [name] if name else list(self._strategies)
        for n in targets:
            s = self._strategies.get(n)
            if s:
                s["orch"].flatten()

    def set_mode(self, mode: str) -> tuple[bool, str]:
        with self._lifecycle_lock:
            if mode not in ("paper", "live"):
                return (False, "mode must be 'paper' or 'live'")

            with self._state_lock:
                if mode == "live":
                    ok, reason = can_go_live(compute_metrics(self._trades()))
                    if not ok:
                        return (False, f"go-live blocked: {reason}")
                was_running = self._running

            if not self.stop():
                return (False, "previous loop thread still alive; mode unchanged")

            with self._state_lock:
                self.mode = mode
                self._broker = None

            if was_running:
                self.start()
            else:
                self.build()
            return (True, f"mode set to {mode}")

    def reconnect(self) -> tuple[bool, str]:
        """Rebuild the broker (and downstream data clients re-read creds on demand)
        from the now-current active credentials. Preserves armed strategies and
        running-desired; restarts the loop if it was running. Mirrors set_mode."""
        with self._lifecycle_lock:
            with self._state_lock:
                was_running = self._running
            if not self.stop():
                return (False, "previous loop thread still alive; not reconnected")
            with self._state_lock:
                self._broker = None
            try:
                if was_running:
                    self.start()
                else:
                    self.build()
            except Exception as e:
                return (False, f"reconnect failed: {e}")
            return (True, "reconnected")

    @_state_locked
    def reload(self) -> None:
        """Rebuild the live strategy set after arming/disarming or settings changes.

        No-op when idle and never built: arming is persisted to ProfileStore and
        picked up by the next build()/start(). Only rebuilds an existing live set
        (already running, or already built at least once).
        """
        if self._running or self._store is not None:
            self.build()

    # ---- lifecycle ----
    def start(self) -> None:
        with self._lifecycle_lock:
            if self._running:
                return
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError(
                    "previous loop thread still alive; refusing to start a second loop")

            with self._state_lock:
                self.build()
                for s in self._strategies.values():
                    s["orch"].reconcile(datetime.now(timezone.utc))

            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._run_loop, name="swingbot-supervisor", daemon=True)
            try:
                self._thread.start()
            except Exception:
                self._running = False
                self._stop_event.set()
                self._thread = None
                raise

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick_all()
            except Exception as e:
                print(f"[supervisor] cycle error: {e}")
                traceback.print_exc()
            with self._state_lock:
                delay = self._poll_seconds()
            if self._stop_event.wait(delay):
                break

    def stop(self) -> bool:
        # Lifecycle lock remains held across join so concurrent start/set_mode
        # cannot race this transition. Do not take the state lock here: a hung
        # tick may hold it, and stop must still signal and time out.
        # Returns True if the loop is fully stopped (no live thread), False if
        # the thread was still alive after the join timeout. On False the thread
        # reference is retained so a second Start stays blocked.
        with self._lifecycle_lock:
            self._running = False
            self._stop_event.set()
            thread = self._thread
            if thread is None:
                return True
            if thread is threading.current_thread():
                return True
            thread.join(timeout=self._join_timeout)
            if thread.is_alive():
                return False
            if self._thread is thread:
                self._thread = None
            return True

    @_state_locked
    def pause(self) -> None:
        self.paused = True

    @_state_locked
    def resume(self) -> None:
        self.paused = False
        for s in self._strategies.values():
            s["orch"].paused = False

    def _poll_seconds(self) -> int:
        return min((s["profile"].poll_seconds for s in self._strategies.values()),
                   default=60)


def _pos_dict(pos):
    if pos is None:
        return None
    return {"symbol": pos.symbol, "entry_price": pos.entry_price, "qty": pos.qty,
            "stop": pos.stop, "tp": pos.tp,
            "max_hold_until": pos.max_hold_until.isoformat(),
            "entry_ts": pos.entry_ts.isoformat()}


def _pending_dict(strategy, order):
    return {
        "strategy": strategy,
        "symbol": order.symbol,
        "side": order.side.value,
        "requested_qty": order.requested_qty,
        "submitted_at": order.submitted_at.isoformat(),
        "client_order_id": order.client_order_id,
        "broker_order_id": order.broker_order_id,
    }


def _trade_dict(t):
    return {"entry_ts": t.entry_ts.isoformat(), "exit_ts": t.exit_ts.isoformat(),
            "entry_price": t.entry_price, "exit_price": t.exit_price, "qty": t.qty,
            "pnl": t.pnl, "exit_reason": t.exit_reason.value,
            "score_at_entry": t.score_at_entry, "regime_at_entry": t.regime_at_entry.value}


def _cycle_dict(record: CycleRecord) -> dict:
    return {
        "cycle_id": record.cycle_id,
        "strategy": record.strategy,
        "started_at": record.started_at.isoformat(),
        "completed_at": record.completed_at.isoformat(),
        "bar_ts": record.bar_ts.isoformat() if record.bar_ts else None,
        "ingest": record.ingest,
        "reconcile": record.reconcile,
        "manage": record.manage,
        "decide": record.decide,
        "persist": record.persist,
        "decision_code": record.decision_code.value,
        "decision_reason": record.decision_reason,
        "decision_details": record.decision_details,
    }
