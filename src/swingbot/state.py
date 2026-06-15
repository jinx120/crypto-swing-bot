from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime

from swingbot.portfolio_risk import PortfolioRiskState
from swingbot.risk import RiskState
from swingbot.types import ExitReason, OpenPosition, OrderSide, PendingOrder, Regime, Side

_DEFAULT = "default"


class StateStore:
    """SQLite persistence for per-strategy open positions and risk state, plus a
    single portfolio-level risk-state row.

    Positions and risk states are keyed by a strategy key (default "default" so
    existing single-strategy callers work unchanged). The broker remains the
    source of truth for positions; this store survives restarts.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS positions (strategy TEXT PRIMARY KEY, data TEXT)")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS pending_orders "
                "(strategy TEXT PRIMARY KEY, data TEXT NOT NULL)")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS risk_states (strategy TEXT PRIMARY KEY, data TEXT)")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS portfolio_risk (id INTEGER PRIMARY KEY, data TEXT)")
        self._migrate_legacy()

    def _migrate_legacy(self) -> None:
        """Move any legacy single-row position/risk_state (id=1) into the keyed
        tables under the default key, once."""
        with self._lock, self._conn:
            for legacy, target in (("position", "positions"), ("risk_state", "risk_states")):
                exists = self._conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (legacy,)
                ).fetchone()
                if not exists:
                    continue
                row = self._conn.execute(f"SELECT data FROM {legacy} WHERE id=1").fetchone()
                if row is None:
                    continue
                already = self._conn.execute(
                    f"SELECT 1 FROM {target} WHERE strategy=?", (_DEFAULT,)).fetchone()
                if already is None:
                    self._conn.execute(
                        f"INSERT INTO {target} (strategy, data) VALUES (?, ?)", (_DEFAULT, row[0]))

    # --- positions (keyed) ---
    def save_position(self, pos: OpenPosition, strategy: str = _DEFAULT) -> None:
        payload = {
            "symbol": pos.symbol, "entry_ts": pos.entry_ts.isoformat(),
            "entry_price": pos.entry_price, "qty": pos.qty, "stop": pos.stop, "tp": pos.tp,
            "max_hold_until": pos.max_hold_until.isoformat(),
            "score_at_entry": pos.score_at_entry,
            "regime_at_entry": pos.regime_at_entry.value, "side": pos.side.value,
            "entry_order_id": pos.entry_order_id,
        }
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO positions (strategy, data) VALUES (?, ?)",
                (strategy, json.dumps(payload)))

    def load_position(self, strategy: str = _DEFAULT) -> OpenPosition | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM positions WHERE strategy=?", (strategy,)).fetchone()
        return self._pos_from_json(row[0]) if row else None

    def clear_position(self, strategy: str = _DEFAULT) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM positions WHERE strategy=?", (strategy,))

    def load_all_positions(self) -> dict[str, OpenPosition]:
        with self._lock:
            rows = self._conn.execute("SELECT strategy, data FROM positions").fetchall()
        return {s: self._pos_from_json(d) for s, d in rows}

    @staticmethod
    def _pos_from_json(data: str) -> OpenPosition:
        d = json.loads(data)
        return OpenPosition(
            symbol=d["symbol"], entry_ts=datetime.fromisoformat(d["entry_ts"]),
            entry_price=d["entry_price"], qty=d["qty"], stop=d["stop"], tp=d["tp"],
            max_hold_until=datetime.fromisoformat(d["max_hold_until"]),
            score_at_entry=d["score_at_entry"], regime_at_entry=Regime(d["regime_at_entry"]),
            side=Side(d["side"]), entry_order_id=d.get("entry_order_id"))

    # --- pending orders (keyed) ---
    def save_pending_order(self, order: PendingOrder, strategy: str = _DEFAULT) -> None:
        payload = {
            "client_order_id": order.client_order_id,
            "broker_order_id": order.broker_order_id,
            "symbol": order.symbol,
            "side": order.side.value,
            "submitted_at": order.submitted_at.isoformat(),
            "requested_qty": order.requested_qty,
            "stop": order.stop,
            "tp": order.tp,
            "max_hold_until": order.max_hold_until.isoformat(),
            "score_at_entry": order.score_at_entry,
            "regime_at_entry": order.regime_at_entry.value,
            "exit_reason": order.exit_reason.value if order.exit_reason else None,
            "observed_exit_price": order.observed_exit_price,
        }
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO pending_orders (strategy, data) VALUES (?, ?)",
                (strategy, json.dumps(payload)),
            )

    def load_pending_order(self, strategy: str = _DEFAULT) -> PendingOrder | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM pending_orders WHERE strategy=?", (strategy,)
            ).fetchone()
        return self._pending_from_json(row[0]) if row else None

    def clear_pending_order(self, strategy: str = _DEFAULT) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM pending_orders WHERE strategy=?", (strategy,))

    def load_all_pending_orders(self) -> dict[str, PendingOrder]:
        with self._lock:
            rows = self._conn.execute("SELECT strategy, data FROM pending_orders").fetchall()
        return {strategy: self._pending_from_json(data) for strategy, data in rows}

    @staticmethod
    def _pending_from_json(data: str) -> PendingOrder:
        payload = json.loads(data)
        return PendingOrder(
            client_order_id=payload["client_order_id"],
            broker_order_id=payload["broker_order_id"],
            symbol=payload["symbol"],
            side=OrderSide(payload["side"]),
            submitted_at=datetime.fromisoformat(payload["submitted_at"]),
            requested_qty=payload["requested_qty"],
            stop=payload["stop"],
            tp=payload["tp"],
            max_hold_until=datetime.fromisoformat(payload["max_hold_until"]),
            score_at_entry=payload["score_at_entry"],
            regime_at_entry=Regime(payload["regime_at_entry"]),
            exit_reason=ExitReason(payload["exit_reason"]) if payload["exit_reason"] else None,
            observed_exit_price=payload["observed_exit_price"],
        )

    # --- per-strategy risk state (keyed) ---
    def save_risk_state(self, rs: RiskState, strategy: str = _DEFAULT) -> None:
        payload = {
            "kill_switch_active": rs.kill_switch_active,
            "kill_switch_reason": rs.kill_switch_reason, "day": rs.day,
            "realized_pnl_today": rs.realized_pnl_today,
            "consecutive_losses": rs.consecutive_losses,
            "day_start_equity": rs.day_start_equity, "cooldown_until": rs.cooldown_until,
        }
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO risk_states (strategy, data) VALUES (?, ?)",
                (strategy, json.dumps(payload)))

    def load_risk_state(self, strategy: str = _DEFAULT) -> RiskState:
        with self._lock:
            row = self._conn.execute(
                "SELECT data FROM risk_states WHERE strategy=?", (strategy,)).fetchone()
        if row is None:
            return RiskState()
        d = json.loads(row[0])
        return RiskState(
            kill_switch_active=d["kill_switch_active"],
            kill_switch_reason=d["kill_switch_reason"], day=d["day"],
            realized_pnl_today=d["realized_pnl_today"],
            consecutive_losses=d["consecutive_losses"],
            day_start_equity=d["day_start_equity"], cooldown_until=d["cooldown_until"])

    # --- portfolio risk state (single row) ---
    def save_portfolio_risk_state(self, prs: PortfolioRiskState) -> None:
        payload = {
            "kill_switch_active": prs.kill_switch_active,
            "kill_switch_reason": prs.kill_switch_reason, "day": prs.day,
            "realized_pnl_today": prs.realized_pnl_today,
            "day_start_equity": prs.day_start_equity,
        }
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO portfolio_risk (id, data) VALUES (1, ?)",
                (json.dumps(payload),))

    def load_portfolio_risk_state(self) -> PortfolioRiskState:
        with self._lock:
            row = self._conn.execute("SELECT data FROM portfolio_risk WHERE id=1").fetchone()
        if row is None:
            return PortfolioRiskState()
        d = json.loads(row[0])
        return PortfolioRiskState(
            kill_switch_active=d["kill_switch_active"],
            kill_switch_reason=d["kill_switch_reason"], day=d["day"],
            realized_pnl_today=d["realized_pnl_today"],
            day_start_equity=d["day_start_equity"])


class StrategyStateView:
    """Binds a StateStore to one strategy key, exposing the no-arg position/risk
    interface the Orchestrator expects."""

    def __init__(self, store: StateStore, strategy: str):
        self._store = store
        self._key = strategy

    def save_position(self, pos: OpenPosition) -> None:
        self._store.save_position(pos, self._key)

    def load_position(self) -> OpenPosition | None:
        return self._store.load_position(self._key)

    def clear_position(self) -> None:
        self._store.clear_position(self._key)

    def save_pending_order(self, order: PendingOrder) -> None:
        self._store.save_pending_order(order, self._key)

    def load_pending_order(self) -> PendingOrder | None:
        return self._store.load_pending_order(self._key)

    def clear_pending_order(self) -> None:
        self._store.clear_pending_order(self._key)

    def save_risk_state(self, rs: RiskState) -> None:
        self._store.save_risk_state(rs, self._key)

    def load_risk_state(self) -> RiskState:
        return self._store.load_risk_state(self._key)
