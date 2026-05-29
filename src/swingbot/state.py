from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from swingbot.risk import RiskState
from swingbot.types import OpenPosition, Regime, Side


class StateStore:
    """SQLite persistence for the open position and risk state.

    Single-row tables (id=1). The broker remains the source of truth for
    positions; this store survives restarts and holds risk counters.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS position (id INTEGER PRIMARY KEY, data TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS risk_state (id INTEGER PRIMARY KEY, data TEXT)"
        )
        self._conn.commit()

    # --- position ---
    def save_position(self, pos: OpenPosition) -> None:
        payload = {
            "symbol": pos.symbol,
            "entry_ts": pos.entry_ts.isoformat(),
            "entry_price": pos.entry_price,
            "qty": pos.qty,
            "stop": pos.stop,
            "tp": pos.tp,
            "max_hold_until": pos.max_hold_until.isoformat(),
            "score_at_entry": pos.score_at_entry,
            "regime_at_entry": pos.regime_at_entry.value,
            "side": pos.side.value,
        }
        self._conn.execute(
            "INSERT OR REPLACE INTO position (id, data) VALUES (1, ?)",
            (json.dumps(payload),),
        )
        self._conn.commit()

    def load_position(self) -> OpenPosition | None:
        row = self._conn.execute("SELECT data FROM position WHERE id=1").fetchone()
        if row is None:
            return None
        d = json.loads(row[0])
        return OpenPosition(
            symbol=d["symbol"],
            entry_ts=datetime.fromisoformat(d["entry_ts"]),
            entry_price=d["entry_price"],
            qty=d["qty"],
            stop=d["stop"],
            tp=d["tp"],
            max_hold_until=datetime.fromisoformat(d["max_hold_until"]),
            score_at_entry=d["score_at_entry"],
            regime_at_entry=Regime(d["regime_at_entry"]),
            side=Side(d["side"]),
        )

    def clear_position(self) -> None:
        self._conn.execute("DELETE FROM position WHERE id=1")
        self._conn.commit()

    # --- risk state ---
    def save_risk_state(self, rs: RiskState) -> None:
        payload = {
            "kill_switch_active": rs.kill_switch_active,
            "kill_switch_reason": rs.kill_switch_reason,
            "day": rs.day,
            "realized_pnl_today": rs.realized_pnl_today,
            "consecutive_losses": rs.consecutive_losses,
            "day_start_equity": rs.day_start_equity,
            "cooldown_until": rs.cooldown_until,
        }
        self._conn.execute(
            "INSERT OR REPLACE INTO risk_state (id, data) VALUES (1, ?)",
            (json.dumps(payload),),
        )
        self._conn.commit()

    def load_risk_state(self) -> RiskState:
        row = self._conn.execute("SELECT data FROM risk_state WHERE id=1").fetchone()
        if row is None:
            return RiskState()
        d = json.loads(row[0])
        return RiskState(
            kill_switch_active=d["kill_switch_active"],
            kill_switch_reason=d["kill_switch_reason"],
            day=d["day"],
            realized_pnl_today=d["realized_pnl_today"],
            consecutive_losses=d["consecutive_losses"],
            day_start_equity=d["day_start_equity"],
            cooldown_until=d["cooldown_until"],
        )
