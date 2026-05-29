from __future__ import annotations

import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Protocol

from swingbot.broker.alpaca import AlpacaBroker
from swingbot.credentials import CredentialStore
from swingbot.data.alpaca import AlpacaData
from swingbot.graduation import can_go_live
from swingbot.journal import TradeJournal
from swingbot.metrics import compute_metrics
from swingbot.orchestrator import Orchestrator
from swingbot.profile import StrategyProfile
from swingbot.profiles import ProfileStore
from swingbot.risk import RiskManager
from swingbot.snapshot import signal_snapshot
from swingbot.state import StateStore
from swingbot.types import MarketContext


class BotController(Protocol):
    def status(self) -> dict: ...
    def journal(self) -> list[dict]: ...
    def metrics(self) -> dict: ...
    def halt(self) -> None: ...
    def reset(self) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def flatten(self) -> None: ...
    def set_mode(self, mode: str) -> tuple[bool, str]: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...


class BotService:
    """Runs the Orchestrator in a background thread; exposes control + status."""

    def __init__(self, profiles: ProfileStore, creds: CredentialStore,
                 state_db: str, mode: str = "paper"):
        self.profiles = profiles
        self.creds = creds
        self.state_db = state_db
        self.mode = mode
        self.orch: Orchestrator | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    def _build(self) -> Orchestrator:
        pdict = self.profiles.get_active()
        if pdict is None:
            raise RuntimeError("no active strategy profile set")
        profile = StrategyProfile.from_dict(pdict)
        c = self.creds.get()
        if c is None:
            raise RuntimeError("Alpaca credentials not set")
        data = AlpacaData(c.key_id, c.secret_key)
        broker = AlpacaBroker(c.key_id, c.secret_key, paper=(self.mode == "paper"))
        state = StateStore(self.state_db)
        risk = RiskManager(profile, state.load_risk_state())
        return Orchestrator(profile=profile, data=data, broker=broker, state=state,
                            risk=risk, journal=TradeJournal())

    def start(self) -> None:
        if self._running:
            return
        self.orch = self._build()
        self.orch.reconcile(datetime.now(timezone.utc))
        self._running = True

        def loop():
            while self._running:
                try:
                    self.orch.tick()
                except Exception as e:
                    print(f"[bot] tick error: {e}")
                time.sleep(self.orch.profile.poll_seconds)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def pause(self) -> None:
        if self.orch:
            self.orch.paused = True

    def resume(self) -> None:
        if self.orch:
            self.orch.paused = False

    def halt(self) -> None:
        if self.orch:
            self.orch.risk.state.kill_switch_active = True
            self.orch.risk.state.kill_switch_reason = "manual halt"
            self.orch.state.save_risk_state(self.orch.risk.state)

    def reset(self) -> None:
        if self.orch:
            self.orch.risk.state.kill_switch_active = False
            self.orch.risk.state.kill_switch_reason = ""
            self.orch.state.save_risk_state(self.orch.risk.state)

    def flatten(self) -> None:
        if self.orch:
            self.orch.flatten()

    def set_mode(self, mode: str) -> tuple[bool, str]:
        if mode not in ("paper", "live"):
            return (False, "mode must be 'paper' or 'live'")
        if mode == "live":
            ok, reason = can_go_live(compute_metrics(self._journal_trades()))
            if not ok:
                return (False, f"go-live blocked: {reason}")
        was_running = self._running
        self.stop()
        self.mode = mode
        if was_running:
            self.start()
        return (True, f"mode set to {mode}")

    def _journal_trades(self):
        return self.orch.journal.trades if self.orch else []

    def status(self) -> dict:
        if not self.orch:
            return {"mode": self.mode, "running": self._running, "active": None}
        o = self.orch
        pos = o.state.load_position()
        rs = o.risk.state
        try:
            df = o.data.get_candles(o.profile.symbol, o.profile.timeframe, o.profile.regime_ma_period + 5)
            bench = None
            if any(s == "relative_strength" for s in o.profile.signals):
                bench = o.data.get_candles(o.profile.benchmark_symbol, o.profile.timeframe, o.profile.regime_ma_period + 5)
            snap = signal_snapshot(o.profile, MarketContext(candles=df, benchmark=bench))
        except Exception as e:
            snap = {"error": str(e)}
        return {
            "mode": self.mode, "running": self._running, "paused": o.paused,
            "symbol": o.profile.symbol,
            "kill_switch": {"active": rs.kill_switch_active, "reason": rs.kill_switch_reason},
            "day_pnl": rs.realized_pnl_today, "consecutive_losses": rs.consecutive_losses,
            "position": _pos_dict(pos),
            "signal": snap,
        }

    def journal(self) -> list[dict]:
        return [_trade_dict(t) for t in self._journal_trades()]

    def metrics(self) -> dict:
        return asdict(compute_metrics(self._journal_trades()))


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
