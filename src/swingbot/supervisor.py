from __future__ import annotations

import threading
import traceback
from datetime import datetime, timezone
from functools import wraps

import pandas as pd

from swingbot.broker.alpaca import AlpacaBroker
from swingbot.data.market import MarketData, timeframe_seconds
from swingbot.journal import TradeJournal
from swingbot.orchestrator import Orchestrator
from swingbot.portfolio_risk import PortfolioRiskManager, PortfolioSettings
from swingbot.profile import StrategyProfile
from swingbot.profiles import ProfileStore
from swingbot.risk import RiskManager
from swingbot.snapshot import signal_snapshot
from dataclasses import asdict, fields

from swingbot.graduation import can_go_live
from swingbot.metrics import compute_metrics
from swingbot.state import StateStore, StrategyStateView
from swingbot.types import MarketContext

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

    def get_candles(self, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame:
        bars = self.market.get(symbol, timeframe, lookback,
                               max_age=timeframe_seconds(timeframe))
        return _bars_to_df(bars)

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
                 runtime_state=None):
        self.profiles = profiles
        self.creds = creds
        self.state_db = state_db
        self.market = market
        self.mode = mode
        self.runtime_state = runtime_state    # durable running_desired flag (may be None)
        self.startup_error: str | None = None  # most recent auto-start outcome
        self._broker = broker
        self.paused = False
        self._running = False
        self._thread: threading.Thread | None = None
        self._latest_prices: dict = {}
        self._timeframes: dict = {}
        self._strategies: dict = {}          # name -> {profile, orch, view, journal, snapshot}
        self._portfolio_risk: PortfolioRiskManager | None = None
        self._store: StateStore | None = None
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
        if self.market is None:
            raise RuntimeError("market must be provided (webmain wires MarketData)")
        if self._broker is None:
            c = self.creds.get() if self.creds else None
            if c is None:
                raise RuntimeError("Alpaca credentials not set")
            self._broker = AlpacaBroker(c.key_id, c.secret_key, paper=(self.mode == "paper"))

        self._store = StateStore(self.state_db)
        # Only the risk-relevant keys belong to PortfolioSettings; other portfolio
        # settings (e.g. default_symbol, a UI concern) are filtered out here.
        _risk_keys = {f.name for f in fields(PortfolioSettings)}
        settings = PortfolioSettings(**{
            k: v for k, v in self.profiles.get_portfolio_settings().items()
            if k in _risk_keys})
        self._portfolio_risk = PortfolioRiskManager(
            settings, self._store.load_portfolio_risk_state())

        provider = CachedProvider(self.market, self._latest_prices, self._timeframes)
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
                risk=risk, journal=TradeJournal(),
                portfolio_gate=self._make_gate(profile),
                portfolio_on_close=self._make_on_close())
            self._strategies[name] = {"profile": profile, "orch": orch,
                                      "view": view, "snapshot": {}}

    def _make_gate(self, profile: StrategyProfile):
        def gate(symbol: str, prospective_value: float):
            positions = self._store.load_all_positions()
            deployed = 0.0
            for pos in positions.values():
                price = self._latest_prices.get(pos.symbol, pos.entry_price)
                deployed += pos.qty * price
            equity = self._broker.get_account()["equity"]
            return self._portfolio_risk.check_can_enter(
                equity=equity, open_position_count=len(positions),
                deployed_value=deployed, prospective_value=prospective_value)
        return gate

    def _make_on_close(self):
        def on_close(pnl: float, now: datetime):
            self._portfolio_risk.on_trade_closed(pnl, now)
            self._store.save_portfolio_risk_state(self._portfolio_risk.state)
        return on_close

    # ---- the loop ----
    @_state_locked
    def tick_all(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._warm(now)
        acct = self._broker.get_account()
        self._portfolio_risk.start_day(now, acct["equity"])
        for name in sorted(self._strategies):                 # deterministic priority
            s = self._strategies[name]
            if self.paused:
                s["orch"].paused = True
            try:
                s["orch"].tick(now)
            except Exception as e:                            # one bad strategy never aborts the cycle
                print(f"[supervisor] {name} tick error: {e}")
            s["snapshot"] = self._snapshot(s["profile"])
        self._store.save_portfolio_risk_state(self._portfolio_risk.state)
        self._summary = self._build_summary(acct)

    def _warm(self, now: datetime) -> None:
        by_tf: dict = {}
        for s in self._strategies.values():
            by_tf.setdefault(s["profile"].timeframe, set()).add(s["profile"].symbol)
        for tf, syms in by_tf.items():
            try:
                self.market.refresh_many(sorted(syms), tf)
            except Exception as e:
                print(f"[supervisor] warm {tf} error: {e}")
        prov = self.market._provider()
        all_syms = sorted({s["profile"].symbol for s in self._strategies.values()})
        if prov is not None and all_syms and hasattr(prov, "get_latest_prices"):
            try:
                self._latest_prices.update(prov.get_latest_prices(all_syms))
            except Exception as e:
                print(f"[supervisor] latest-price error: {e}")

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

    # ---- status + control surface (consumed by Phase 2 web layer) ----
    @_state_locked
    def status(self) -> dict:
        strategies = []
        if self._strategies:
            for name in sorted(self._strategies):
                s = self._strategies[name]
                pos = s["view"].load_position()
                rs = s["orch"].risk.state
                strategies.append({
                    "name": name, "symbol": s["profile"].symbol,
                    "running": self._running,
                    "live_eligible": self.profiles.is_live_eligible(name),
                    "snapshot": s["snapshot"],
                    "position": _pos_dict(pos),
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
                strategies.append({
                    "name": name, "symbol": symbol,
                    "running": False,
                    "live_eligible": f["live_eligible"],
                    "snapshot": {}, "position": None, "risk": None,
                })
        return {"portfolio": self._summary or {"mode": self.mode, "running": self._running},
                "strategies": strategies}

    def lifecycle_state(self) -> dict:
        with self._lifecycle_lock:
            thread_alive = bool(self._thread is not None and self._thread.is_alive())
            running_flag = bool(self._running)
            with self._state_lock:
                halted = bool(
                    self._portfolio_risk
                    and self._portfolio_risk.state.kill_switch_active)
                return {
                    "mode": self.mode,
                    "running_flag": running_flag,
                    "thread_alive": thread_alive,
                    "running_actual": thread_alive,
                    "running_desired": self.running_desired,
                    "paused": bool(self.paused),
                    "halted": halted,
                    "startup_error": self.startup_error,
                }

    # ---- aggregate journal + metrics ----
    def _trades(self, strategy: str | None = None) -> list:
        out = []
        for name, s in self._strategies.items():
            if strategy and name != strategy:
                continue
            out.extend(s["orch"].journal.trades)
        return out

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


def _trade_dict(t):
    return {"entry_ts": t.entry_ts.isoformat(), "exit_ts": t.exit_ts.isoformat(),
            "entry_price": t.entry_price, "exit_price": t.exit_price, "qty": t.qty,
            "pnl": t.pnl, "exit_reason": t.exit_reason.value,
            "score_at_entry": t.score_at_entry, "regime_at_entry": t.regime_at_entry.value}
