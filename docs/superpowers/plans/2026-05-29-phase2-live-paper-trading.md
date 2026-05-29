# Phase 2 — Paper/Live Trading (Broker + Risk + State + Orchestrator) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Phase 1 backtest engine into a live/paper trading bot on Alpaca crypto: real market data, a real broker adapter, a risk gatekeeper with four circuit breakers, persistent state, and an always-on orchestrator loop — reusing every Phase 1 strategy module unchanged.

**Architecture:** A single always-on Python process. Strategy logic (signals, regime, confluence, sizing, exit rules) is reused verbatim from Phase 1. Alpaca crypto has **no broker-side brackets/stops** (only market/limit/stop_limit, TIF gtc/ioc), so **exits are managed client-side**: the orchestrator polls the latest price each tick and submits a market sell when the stop, take-profit, or time-cap fires. The exit *rule* is extracted into one pure function shared by the backtest `SimulatedBroker` and the live path so the two never drift. Risk decisions (circuit breakers + sizing) live in a pure `RiskManager` operating on an in-memory `RiskState` that a SQLite `StateStore` persists and reloads (broker is reconciled as source of truth on startup).

**Tech Stack:** Python 3.11+, `alpaca-py` (Alpaca SDK), `pandas`, `numpy`, SQLite (stdlib `sqlite3`), `pytest`. No new heavyweight deps; a tiny hand-rolled `.env` loader avoids `python-dotenv`.

---

## Important Alpaca Crypto Constraints (drive this whole phase)

- Order types for crypto: **market, limit, stop_limit only**. No `stop`, no `trailing_stop`.
- Order classes: **no bracket, no OCO, no OTO**. Stop-loss / take-profit legs **cannot** be attached.
- Time-in-force for crypto: **gtc or ioc only**.
- Therefore: the bot holds the position and **closes it itself** with a market sell when an exit condition is met. The `SimulatedBroker` (backtest) already does this internally; the live path replicates the *same decision rule* via the shared `exit_decision` function.

---

## File Structure

```
src/swingbot/
  types.py                 # MODIFY: add OpenPosition dataclass
  profile.py               # MODIFY: add risk/circuit-breaker config fields
  exits.py                 # MODIFY: add exit_decision() pure function (keep bracket_levels)
  broker/
    simulated.py           # MODIFY: refactor update() to call exit_decision()
    alpaca.py              # CREATE: AlpacaBroker (live/paper) via alpaca-py TradingClient
  data/
    alpaca.py              # CREATE: AlpacaData provider via alpaca-py crypto data client
  config.py                # CREATE: .env loader + load_alpaca_credentials()
  state.py                 # CREATE: SQLite StateStore + RiskState (de)serialization
  risk.py                  # CREATE: RiskManager + RiskState + RiskDecision (4 circuit breakers + sizing)
  orchestrator.py          # CREATE: Orchestrator.tick() + run() loop
  run.py                   # CREATE: `swingbot-run` CLI entrypoint (paper/live)
tests/
  test_exit_decision.py        # CREATE
  test_profile_risk.py         # CREATE
  test_config.py               # CREATE
  test_state.py                # CREATE
  test_risk.py                 # CREATE
  test_orchestrator.py         # CREATE (uses in-memory fakes — fully offline)
  test_alpaca_data.py          # CREATE (pure helpers offline; live calls cred-gated/skipped)
  test_alpaca_broker.py        # CREATE (pure helpers offline; live calls cred-gated/skipped)
pyproject.toml             # MODIFY: add alpaca-py dependency + swingbot-run script
```

**Design seams:**
- `RiskManager` is pure (no SQLite, no network) — operates on a `RiskState` object. `StateStore` handles persistence. This keeps the most important logic fully unit-testable.
- `Orchestrator.tick()` takes injected `data`, `broker`, `state`, etc., so tests drive it with in-memory fakes — **no network needed to test the integration logic**.
- All Alpaca network tests are skipped unless `ALPACA_API_KEY_ID`/`ALPACA_API_SECRET_KEY` are in `os.environ`, so `pytest` stays green offline.

---

## Task 1: Profile risk config + OpenPosition type

**Files:**
- Modify: `src/swingbot/profile.py`
- Modify: `src/swingbot/types.py`
- Test: `tests/test_profile_risk.py`

- [ ] **Step 1: Write the failing test** `tests/test_profile_risk.py`

```python
from datetime import datetime, timezone

from swingbot.profile import StrategyProfile
from swingbot.types import OpenPosition, Regime, Side


def test_profile_has_risk_defaults():
    p = StrategyProfile.from_dict({"symbol": "TRX/USD"})
    assert p.daily_loss_limit_pct == 0.05
    assert p.max_consecutive_losses == 4
    assert p.max_concurrent == 1
    assert p.cooldown_minutes == 60
    assert p.poll_seconds == 60

def test_profile_risk_overrides():
    p = StrategyProfile.from_dict({"symbol": "TRX/USD", "max_concurrent": 2,
                                   "cooldown_minutes": 30})
    assert p.max_concurrent == 2
    assert p.cooldown_minutes == 30

def test_open_position_roundtrips_fields():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    op = OpenPosition(symbol="TRX/USD", entry_ts=now, entry_price=0.1, qty=100.0,
                      stop=0.09, tp=0.12, max_hold_until=now,
                      score_at_entry=0.7, regime_at_entry=Regime.UPTREND, side=Side.LONG)
    assert op.symbol == "TRX/USD"
    assert op.qty == 100.0
    assert op.side == Side.LONG
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_profile_risk.py -v`
Expected: ImportError (`OpenPosition`) / AttributeError on the new fields.

- [ ] **Step 3: Add risk fields to `src/swingbot/profile.py`**

Insert these fields into the `StrategyProfile` dataclass immediately after the existing `max_position_frac` line (before the `# backtest cost model` comment):

```python
    # circuit breakers (Phase 2)
    daily_loss_limit_pct: float = 0.05   # halt new entries after -5% day
    max_consecutive_losses: int = 4      # ...or after N losses in a row
    max_concurrent: int = 1              # max simultaneous open positions
    cooldown_minutes: int = 60           # wait after a stop-out before re-entering
    poll_seconds: int = 60               # orchestrator loop interval
```

- [ ] **Step 4: Add `OpenPosition` to `src/swingbot/types.py`**

Append at the end of the file:

```python
@dataclass
class OpenPosition:
    """A live open position, persisted by the StateStore."""
    symbol: str
    entry_ts: datetime
    entry_price: float
    qty: float
    stop: float
    tp: float
    max_hold_until: datetime
    score_at_entry: float
    regime_at_entry: Regime
    side: Side = Side.LONG
```

- [ ] **Step 5: Run, confirm PASS**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_profile_risk.py -v`
Expected: 3 passed.

- [ ] **Step 6: Run full suite (no regressions)**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest -q`
Expected: all pass (43 + 3 = 46).

- [ ] **Step 7: Commit**

```bash
git add src/swingbot/profile.py src/swingbot/types.py tests/test_profile_risk.py
git commit -m "feat: add circuit-breaker config + OpenPosition type"
```

---

## Task 2: Extract shared exit_decision; refactor SimulatedBroker

**Files:**
- Modify: `src/swingbot/exits.py`
- Modify: `src/swingbot/broker/simulated.py`
- Test: `tests/test_exit_decision.py`

**Why:** The live path has only a latest *price* (not a full bar). We extract the exit *rule* into one pure function so backtest and live use identical logic. Backtest passes a bar's high/low/close; live passes `high=low=close=latest_price`.

- [ ] **Step 1: Write the failing test** `tests/test_exit_decision.py`

```python
from datetime import datetime, timedelta, timezone

from swingbot.exits import exit_decision
from swingbot.types import ExitReason

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
LATER = T0 + timedelta(hours=9)


def test_stop_before_tp_same_bar():
    # bar touches both stop (low) and tp (high); stop wins (conservative)
    res = exit_decision(stop=95.0, tp=110.0, max_hold_until=LATER,
                        high=111.0, low=94.0, close=100.0, now=T0)
    assert res == (ExitReason.STOP, 95.0)

def test_take_profit():
    res = exit_decision(stop=95.0, tp=110.0, max_hold_until=LATER,
                        high=111.0, low=99.0, close=108.0, now=T0)
    assert res == (ExitReason.TAKE_PROFIT, 110.0)

def test_time_cap_fills_at_close():
    res = exit_decision(stop=90.0, tp=120.0, max_hold_until=T0,
                        high=105.0, low=96.0, close=101.0, now=T0)
    assert res == (ExitReason.TIME_CAP, 101.0)

def test_no_exit():
    res = exit_decision(stop=90.0, tp=120.0, max_hold_until=LATER,
                        high=105.0, low=96.0, close=101.0, now=T0)
    assert res is None

def test_live_spot_price_stop(monkeypatch=None):
    # live usage: high=low=close=latest price below stop
    res = exit_decision(stop=95.0, tp=110.0, max_hold_until=LATER,
                        high=94.5, low=94.5, close=94.5, now=T0)
    assert res == (ExitReason.STOP, 95.0)
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_exit_decision.py -v`
Expected: ImportError (`exit_decision`).

- [ ] **Step 3: Add `exit_decision` to `src/swingbot/exits.py`**

Append to the file (keep the existing `bracket_levels`):

```python
from datetime import datetime

from swingbot.types import ExitReason


def exit_decision(
    stop: float, tp: float, max_hold_until: datetime,
    high: float, low: float, close: float, now: datetime,
) -> tuple[ExitReason, float] | None:
    """Decide whether a long position exits, and a reference exit price.

    Priority: STOP, then TAKE_PROFIT, then TIME_CAP. For live use, pass
    high=low=close=latest_price. The returned price is the modeled fill for
    backtest; live callers submit a market order and use the actual fill.
    """
    if low <= stop:
        return (ExitReason.STOP, stop)
    if high >= tp:
        return (ExitReason.TAKE_PROFIT, tp)
    if now >= max_hold_until:
        return (ExitReason.TIME_CAP, close)
    return None
```

Note: add the two new imports (`from datetime import datetime` and `from swingbot.types import ExitReason`) at the top of `exits.py` if not already present; keep `from __future__ import annotations` as the first line.

- [ ] **Step 4: Refactor `SimulatedBroker.update` to use it**

In `src/swingbot/broker/simulated.py`, add the import near the top:
```python
from swingbot.exits import exit_decision
```
Replace the body of `update` (the block computing `exit_price`/`reason`) with:

```python
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
```

- [ ] **Step 5: Run new test + FULL suite (no regressions in backtest)**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_exit_decision.py -v && pytest -q`
Expected: 5 new passed; full suite all pass (now 46 + 5 = 51). The existing `tests/test_simulated_broker.py` must still pass unchanged — proving the refactor preserved behavior.

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/exits.py src/swingbot/broker/simulated.py tests/test_exit_decision.py
git commit -m "refactor: shared exit_decision used by SimulatedBroker (and live path later)"
```

---

## Task 3: Credential / .env loader

**Files:**
- Create: `src/swingbot/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test** `tests/test_config.py`

```python
import pytest

from swingbot.config import load_dotenv, load_alpaca_credentials, AlpacaCredentials


def test_load_dotenv_sets_missing_keys(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nFOO_KEY=abc123\nBAR='quoted val'\n\nEMPTY=\n")
    monkeypatch.delenv("FOO_KEY", raising=False)
    monkeypatch.delenv("BAR", raising=False)
    load_dotenv(str(env))
    import os
    assert os.environ["FOO_KEY"] == "abc123"
    assert os.environ["BAR"] == "quoted val"

def test_load_dotenv_does_not_override_existing(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("FOO_KEY=fromfile\n")
    monkeypatch.setenv("FOO_KEY", "fromenv")
    load_dotenv(str(env))
    import os
    assert os.environ["FOO_KEY"] == "fromenv"

def test_load_credentials_reads_env(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY_ID", "kid")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "sec")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    creds = load_alpaca_credentials()
    assert isinstance(creds, AlpacaCredentials)
    assert creds.key_id == "kid"
    assert creds.secret_key == "sec"
    assert creds.paper is True

def test_load_credentials_missing_raises(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY_ID", raising=False)
    monkeypatch.delenv("ALPACA_API_SECRET_KEY", raising=False)
    with pytest.raises(ValueError, match="ALPACA_API_KEY_ID"):
        load_alpaca_credentials()
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_config.py -v`
Expected: ModuleNotFoundError: `swingbot.config`.

- [ ] **Step 3: Implement `src/swingbot/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass


def load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader: sets KEY=VALUE lines into os.environ.
    Does NOT override variables already present in the environment.
    Ignores blanks and #-comments. Strips surrounding single/double quotes.
    """
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


@dataclass(frozen=True)
class AlpacaCredentials:
    key_id: str
    secret_key: str
    base_url: str
    paper: bool


def load_alpaca_credentials() -> AlpacaCredentials:
    key_id = os.environ.get("ALPACA_API_KEY_ID")
    secret_key = os.environ.get("ALPACA_API_SECRET_KEY")
    base_url = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    if not key_id:
        raise ValueError("ALPACA_API_KEY_ID is not set (check your .env)")
    if not secret_key:
        raise ValueError("ALPACA_API_SECRET_KEY is not set (check your .env)")
    paper = "paper" in base_url
    return AlpacaCredentials(key_id=key_id, secret_key=secret_key,
                             base_url=base_url, paper=paper)
```

- [ ] **Step 4: Run, confirm PASS**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_config.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/config.py tests/test_config.py
git commit -m "feat: .env loader + Alpaca credential loading"
```

---

## Task 4: SQLite StateStore

**Files:**
- Create: `src/swingbot/state.py`
- Test: `tests/test_state.py`

**Responsibility:** Persist and reload: the open position (0 or 1 for v1), and the `RiskState` (kill-switch, daily PnL, consecutive losses, day reference, day-start equity, cooldown timer). `RiskState` itself is defined in Task 5 (`risk.py`); to avoid a task-ordering import problem, define `RiskState` in `risk.py` and have `state.py` import it. **Implement Task 5 before wiring StateStore's RiskState methods if needed**, but the StateStore tests below for RiskState construct it directly — so do Task 5 first if your runner enforces import order. (Subagent note: if `swingbot.risk` doesn't exist yet, do Task 5 first, then Task 4. They are independent otherwise.)

- [ ] **Step 1: Write the failing test** `tests/test_state.py`

```python
from datetime import datetime, timezone

from swingbot.state import StateStore
from swingbot.types import OpenPosition, Regime, Side
from swingbot.risk import RiskState


def _pos(now):
    return OpenPosition(symbol="TRX/USD", entry_ts=now, entry_price=0.10, qty=100.0,
                        stop=0.09, tp=0.12, max_hold_until=now,
                        score_at_entry=0.7, regime_at_entry=Regime.UPTREND, side=Side.LONG)


def test_position_save_load_clear(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert s.load_position() is None
    s.save_position(_pos(now))
    loaded = s.load_position()
    assert loaded.symbol == "TRX/USD"
    assert loaded.qty == 100.0
    assert loaded.regime_at_entry == Regime.UPTREND
    s.clear_position()
    assert s.load_position() is None

def test_risk_state_roundtrip(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    rs = RiskState(kill_switch_active=True, kill_switch_reason="daily loss",
                   day="2026-01-01", realized_pnl_today=-12.5, consecutive_losses=3,
                   day_start_equity=1000.0,
                   cooldown_until={"TRX/USD": "2026-01-01T05:00:00+00:00"})
    s.save_risk_state(rs)
    out = s.load_risk_state()
    assert out.kill_switch_active is True
    assert out.consecutive_losses == 3
    assert out.realized_pnl_today == -12.5
    assert out.cooldown_until["TRX/USD"] == "2026-01-01T05:00:00+00:00"

def test_load_risk_state_default_when_empty(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    rs = s.load_risk_state()
    assert rs.kill_switch_active is False
    assert rs.consecutive_losses == 0
    assert rs.cooldown_until == {}

def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "s.db")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    StateStore(path).save_position(_pos(now))
    assert StateStore(path).load_position().symbol == "TRX/USD"
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_state.py -v`
Expected: ModuleNotFoundError (`swingbot.state` and/or `swingbot.risk`). (Do Task 5 first if `swingbot.risk` is missing.)

- [ ] **Step 3: Implement `src/swingbot/state.py`**

```python
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
```

- [ ] **Step 4: Run, confirm PASS**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_state.py -v`
Expected: 4 passed (requires Task 5's `RiskState`).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/state.py tests/test_state.py
git commit -m "feat: SQLite StateStore for position + risk state"
```

---

## Task 5: RiskManager + circuit breakers

**Files:**
- Create: `src/swingbot/risk.py`
- Test: `tests/test_risk.py`

**Responsibility (pure, no IO):** Gate entries through the four circuit breakers and size positions; update counters when a trade closes; trip the kill switch.

- [ ] **Step 1: Write the failing test** `tests/test_risk.py`

```python
from datetime import datetime, timedelta, timezone

from swingbot.journal import Trade
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager, RiskState
from swingbot.types import ExitReason, Regime, Side

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _profile(**kw):
    base = {"symbol": "TRX/USD", "risk_per_trade": 0.01, "max_position_frac": 0.25,
            "daily_loss_limit_pct": 0.05, "max_consecutive_losses": 4,
            "max_concurrent": 1, "cooldown_minutes": 60}
    base.update(kw)
    return StrategyProfile.from_dict(base)


def _trade(pnl, reason, ts=T0):
    return Trade(entry_ts=ts, exit_ts=ts, side=Side.LONG, entry_price=0.10,
                 exit_price=0.10 + pnl, qty=1.0, pnl=pnl, exit_reason=reason,
                 score_at_entry=0.7, regime_at_entry=Regime.UPTREND)


def test_entry_approved_when_clean():
    rm = RiskManager(_profile(), RiskState(day_start_equity=1000.0))
    d = rm.check_can_enter("TRX/USD", now=T0, open_position_count=0)
    assert d.approved is True

def test_entry_blocked_when_killswitch_active():
    rm = RiskManager(_profile(), RiskState(kill_switch_active=True, kill_switch_reason="x"))
    d = rm.check_can_enter("TRX/USD", now=T0, open_position_count=0)
    assert d.approved is False and "kill" in d.reason.lower()

def test_entry_blocked_when_max_concurrent_reached():
    rm = RiskManager(_profile(max_concurrent=1), RiskState())
    d = rm.check_can_enter("TRX/USD", now=T0, open_position_count=1)
    assert d.approved is False and "concurrent" in d.reason.lower()

def test_entry_blocked_during_cooldown():
    rs = RiskState(cooldown_until={"TRX/USD": (T0 + timedelta(minutes=30)).isoformat()})
    rm = RiskManager(_profile(), rs)
    d = rm.check_can_enter("TRX/USD", now=T0, open_position_count=0)
    assert d.approved is False and "cooldown" in d.reason.lower()

def test_entry_allowed_after_cooldown_expires():
    rs = RiskState(cooldown_until={"TRX/USD": (T0 - timedelta(minutes=1)).isoformat()})
    rm = RiskManager(_profile(), rs)
    d = rm.check_can_enter("TRX/USD", now=T0, open_position_count=0)
    assert d.approved is True

def test_sizing_uses_fixed_fractional():
    rm = RiskManager(_profile(risk_per_trade=0.01), RiskState(day_start_equity=1000.0))
    # equity 1000, risk 1% => $10; stop distance 0.005 => 2000 units
    qty = rm.size(equity=1000.0, entry_price=0.10, stop_price=0.095)
    assert abs(qty - 2000.0) < 1e-6

def test_stop_out_sets_cooldown_and_counts_loss():
    rs = RiskState(day="2026-01-01", day_start_equity=1000.0)
    rm = RiskManager(_profile(cooldown_minutes=60), rs)
    rm.on_trade_closed(_trade(-5.0, ExitReason.STOP), now=T0)
    assert rs.consecutive_losses == 1
    assert "TRX/USD" in rs.cooldown_until
    assert rs.realized_pnl_today == -5.0

def test_win_resets_consecutive_losses():
    rs = RiskState(day="2026-01-01", consecutive_losses=2, day_start_equity=1000.0)
    rm = RiskManager(_profile(), rs)
    rm.on_trade_closed(_trade(3.0, ExitReason.TAKE_PROFIT), now=T0)
    assert rs.consecutive_losses == 0

def test_killswitch_trips_on_consecutive_losses():
    rs = RiskState(day="2026-01-01", consecutive_losses=3, day_start_equity=1000.0)
    rm = RiskManager(_profile(max_consecutive_losses=4), rs)
    rm.on_trade_closed(_trade(-1.0, ExitReason.STOP), now=T0)
    assert rs.kill_switch_active is True

def test_killswitch_trips_on_daily_loss():
    rs = RiskState(day="2026-01-01", realized_pnl_today=-40.0, day_start_equity=1000.0)
    rm = RiskManager(_profile(daily_loss_limit_pct=0.05), rs)  # limit = -50
    rm.on_trade_closed(_trade(-15.0, ExitReason.STOP), now=T0)  # total -55 < -50
    assert rs.kill_switch_active is True

def test_daily_counters_reset_on_new_day():
    rs = RiskState(day="2026-01-01", realized_pnl_today=-40.0, consecutive_losses=3,
                   day_start_equity=1000.0)
    rm = RiskManager(_profile(), rs)
    next_day = T0 + timedelta(days=1)
    rm.start_day(now=next_day, equity=900.0)
    assert rs.day == "2026-01-02"
    assert rs.realized_pnl_today == 0.0
    assert rs.consecutive_losses == 0
    assert rs.day_start_equity == 900.0
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_risk.py -v`
Expected: ModuleNotFoundError: `swingbot.risk`.

- [ ] **Step 3: Implement `src/swingbot/risk.py`**

```python
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
```

- [ ] **Step 4: Run, confirm PASS**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_risk.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/risk.py tests/test_risk.py
git commit -m "feat: RiskManager with four circuit breakers + fixed-fractional sizing"
```

---

## Task 6: Alpaca market data provider

**Files:**
- Modify: `pyproject.toml` (add `alpaca-py` dependency)
- Create: `src/swingbot/data/alpaca.py`
- Test: `tests/test_alpaca_data.py`

**Note on alpaca-py:** API specifics target alpaca-py ≥ 0.2x. The pure helpers (`parse_timeframe`, `bars_to_df`) are unit-tested offline; the live `get_candles`/`get_latest_price` calls are exercised only when credentials are present (otherwise skipped). If the installed alpaca-py version differs, adjust import paths in the network methods only — the helpers and the rest of the system are unaffected.

- [ ] **Step 1: Add dependency to `pyproject.toml`**

In `[project].dependencies`, change the list to include alpaca-py:
```toml
dependencies = ["pandas>=2.0", "numpy>=1.24", "alpaca-py>=0.20"]
```
Then reinstall:
```bash
cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pip install -e ".[dev]" -q
```
Expected: installs `alpaca-py` and its deps without error.

- [ ] **Step 2: Write the failing test** `tests/test_alpaca_data.py`

```python
import os
import pandas as pd
import pytest

from swingbot.data.alpaca import parse_timeframe, bars_to_df

CREDS = bool(os.getenv("ALPACA_API_KEY_ID") and os.getenv("ALPACA_API_SECRET_KEY"))


def test_parse_timeframe_minutes_hours():
    from alpaca.data.timeframe import TimeFrameUnit
    tf = parse_timeframe("15m")
    assert tf.amount_value == 15 and tf.unit_value == TimeFrameUnit.Minute
    tf2 = parse_timeframe("4h")
    assert tf2.amount_value == 4 and tf2.unit_value == TimeFrameUnit.Hour
    tf3 = parse_timeframe("1d")
    assert tf3.amount_value == 1 and tf3.unit_value == TimeFrameUnit.Day

def test_parse_timeframe_rejects_bad():
    with pytest.raises(ValueError):
        parse_timeframe("15x")

def test_bars_to_df_normalizes():
    rows = [
        {"timestamp": pd.Timestamp("2026-01-01T00:00:00Z"), "open": 1, "high": 2,
         "low": 0.5, "close": 1.5, "volume": 10},
        {"timestamp": pd.Timestamp("2026-01-01T00:15:00Z"), "open": 1.5, "high": 2.2,
         "low": 1.4, "close": 2.0, "volume": 12},
    ]
    df = bars_to_df(rows)
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert df["ts"].is_monotonic_increasing
    assert str(df["ts"].dt.tz) == "UTC"
    assert df["close"].dtype == float

@pytest.mark.skipif(not CREDS, reason="Alpaca creds not set")
def test_live_get_candles_smoke():
    from swingbot.data.alpaca import AlpacaData
    d = AlpacaData(os.environ["ALPACA_API_KEY_ID"], os.environ["ALPACA_API_SECRET_KEY"])
    df = d.get_candles("BTC/USD", "15m", lookback=50)
    assert len(df) > 0
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
```

- [ ] **Step 3: Run, confirm FAIL**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_alpaca_data.py -v`
Expected: ModuleNotFoundError: `swingbot.data.alpaca`. (The live smoke test should SKIP, not fail, when no creds.)

- [ ] **Step 4: Implement `src/swingbot/data/alpaca.py`**

```python
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pandas as pd

from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, CryptoLatestTradeRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

_UNITS = {"m": TimeFrameUnit.Minute, "h": TimeFrameUnit.Hour, "d": TimeFrameUnit.Day}
_CANON = ["ts", "open", "high", "low", "close", "volume"]


def parse_timeframe(tf: str) -> TimeFrame:
    m = re.fullmatch(r"(\d+)([mhd])", tf)
    if not m:
        raise ValueError(f"bad timeframe {tf!r}; use like '15m', '4h', '1d'")
    return TimeFrame(int(m.group(1)), _UNITS[m.group(2)])


def bars_to_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df = df.rename(columns={"timestamp": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    return df[_CANON].sort_values("ts").reset_index(drop=True)


class AlpacaData:
    """Alpaca crypto market data. Implements the MarketDataProvider protocol."""

    def __init__(self, key_id: str, secret_key: str):
        self._client = CryptoHistoricalDataClient(key_id, secret_key)

    def get_candles(self, symbol: str, timeframe: str, lookback: int) -> pd.DataFrame:
        tf = parse_timeframe(timeframe)
        # over-fetch a window then take the last `lookback` rows
        start = datetime.now(timezone.utc) - timedelta(days=30)
        req = CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=start)
        bars = self._client.get_crypto_bars(req)
        records = []
        for bar in bars[symbol]:
            records.append({
                "timestamp": bar.timestamp, "open": bar.open, "high": bar.high,
                "low": bar.low, "close": bar.close, "volume": bar.volume,
            })
        df = bars_to_df(records)
        return df.tail(lookback).reset_index(drop=True)

    def get_latest_price(self, symbol: str) -> float:
        req = CryptoLatestTradeRequest(symbol_or_symbols=symbol)
        trade = self._client.get_crypto_latest_trade(req)
        return float(trade[symbol].price)
```

- [ ] **Step 5: Run, confirm PASS (live test SKIPS offline)**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_alpaca_data.py -v`
Expected: 3 passed, 1 skipped (the live smoke test).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/swingbot/data/alpaca.py tests/test_alpaca_data.py
git commit -m "feat: Alpaca crypto market data provider (+ alpaca-py dep)"
```

---

## Task 7: Alpaca broker adapter

**Files:**
- Create: `src/swingbot/broker/alpaca.py`
- Test: `tests/test_alpaca_broker.py`

**Note:** Crypto = market orders only for entries/exits, TIF gtc. No brackets. Pure helper `normalize_symbol` is tested offline; live calls are credential-gated.

- [ ] **Step 1: Write the failing test** `tests/test_alpaca_broker.py`

```python
import os
import pytest

from swingbot.broker.alpaca import normalize_symbol

CREDS = bool(os.getenv("ALPACA_API_KEY_ID") and os.getenv("ALPACA_API_SECRET_KEY"))


def test_normalize_symbol_keeps_slash():
    # Alpaca crypto trading uses "BTC/USD"
    assert normalize_symbol("BTC/USD") == "BTC/USD"
    assert normalize_symbol("btc/usd") == "BTC/USD"

@pytest.mark.skipif(not CREDS, reason="Alpaca creds not set")
def test_live_account_smoke():
    from swingbot.broker.alpaca import AlpacaBroker
    b = AlpacaBroker(os.environ["ALPACA_API_KEY_ID"],
                     os.environ["ALPACA_API_SECRET_KEY"], paper=True)
    acct = b.get_account()
    assert acct["equity"] >= 0
    # no open position for a fresh paper account symbol (may be None)
    _ = b.get_position("BTC/USD")
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_alpaca_broker.py -v`
Expected: ModuleNotFoundError: `swingbot.broker.alpaca` (live test skips offline).

- [ ] **Step 3: Implement `src/swingbot/broker/alpaca.py`**

```python
from __future__ import annotations

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest


def normalize_symbol(symbol: str) -> str:
    """Alpaca crypto trading expects 'BTC/USD' form, uppercased."""
    return symbol.upper()


class AlpacaBroker:
    """Live/paper Alpaca crypto broker. Long-only, market orders (no brackets).

    Exit management (stop/take-profit/time-cap) is handled by the Orchestrator,
    which calls submit_market_sell when an exit fires.
    """

    def __init__(self, key_id: str, secret_key: str, paper: bool = True):
        self._client = TradingClient(key_id, secret_key, paper=paper)

    def get_account(self) -> dict:
        a = self._client.get_account()
        return {"equity": float(a.equity), "cash": float(a.cash),
                "buying_power": float(a.buying_power)}

    def get_position(self, symbol: str) -> dict | None:
        try:
            p = self._client.get_open_position(normalize_symbol(symbol))
        except Exception:
            return None
        return {"symbol": symbol, "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "market_value": float(p.market_value)}

    def submit_market_buy(self, symbol: str, qty: float) -> str:
        req = MarketOrderRequest(symbol=normalize_symbol(symbol), qty=qty,
                                 side=OrderSide.BUY, time_in_force=TimeInForce.GTC)
        order = self._client.submit_order(order_data=req)
        return str(order.id)

    def submit_market_sell(self, symbol: str, qty: float) -> str:
        req = MarketOrderRequest(symbol=normalize_symbol(symbol), qty=qty,
                                 side=OrderSide.SELL, time_in_force=TimeInForce.GTC)
        order = self._client.submit_order(order_data=req)
        return str(order.id)

    def cancel_all(self) -> None:
        self._client.cancel_orders()
```

- [ ] **Step 4: Run, confirm PASS (live test SKIPS offline)**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_alpaca_broker.py -v`
Expected: 1 passed, 1 skipped.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/broker/alpaca.py tests/test_alpaca_broker.py
git commit -m "feat: Alpaca crypto broker adapter (market orders, client-side exits)"
```

---

## Task 8: Orchestrator (tick + run loop)

**Files:**
- Create: `src/swingbot/orchestrator.py`
- Test: `tests/test_orchestrator.py`

**Responsibility:** One `tick()` does the full cycle: refresh day counters; if a position is open, check `exit_decision` against the latest price and close via market sell when it fires (recording the Trade and updating risk/state); if flat, fetch candles, run regime gate → confluence → risk gate, and on approval submit a market buy and persist the new position. `run()` calls `tick()` forever on an interval with error isolation. Tests inject in-memory fakes — **no network**.

- [ ] **Step 1: Write the failing test** `tests/test_orchestrator.py`

```python
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from swingbot.orchestrator import Orchestrator
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager, RiskState
from swingbot.state import StateStore
from swingbot.journal import TradeJournal
from swingbot.types import ExitReason

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _series(closes, end_ts=T0):
    n = len(closes)
    closes = np.array(closes, dtype=float)
    ts = pd.date_range(end=end_ts, periods=n, freq="15min", tz="UTC")
    return pd.DataFrame({"ts": ts, "open": closes, "high": closes * 1.002,
                         "low": closes * 0.998, "close": closes,
                         "volume": np.full(n, 100.0)})


class FakeData:
    def __init__(self, candles, price): self._c = candles; self._price = price
    def set_price(self, p): self._price = p
    def get_candles(self, symbol, timeframe, lookback): return self._c
    def get_latest_price(self, symbol): return self._price


class FakeBroker:
    def __init__(self, equity=1000.0):
        self._equity = equity; self.position = None; self.buys = []; self.sells = []
    def get_account(self): return {"equity": self._equity, "cash": self._equity,
                                   "buying_power": self._equity}
    def get_position(self, symbol): return self.position
    def submit_market_buy(self, symbol, qty):
        self.position = {"symbol": symbol, "qty": qty, "avg_entry_price": 100.0,
                         "market_value": qty * 100.0}
        self.buys.append((symbol, qty)); return "buy-1"
    def submit_market_sell(self, symbol, qty):
        self.position = None; self.sells.append((symbol, qty)); return "sell-1"
    def cancel_all(self): pass


def _profile(**kw):
    base = {"symbol": "TRX/USD", "timeframe": "15m",
            "signals": {"oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
                        "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05}},
            "entry_threshold": 0.25, "regime_ma_period": 50, "atr_period": 14,
            "stop_atr_mult": 2.0, "take_profit_atr_mult": 2.0, "max_hold_bars": 32,
            "risk_per_trade": 0.02, "max_concurrent": 1}
    base.update(kw)
    return StrategyProfile.from_dict(base)


def _orch(data, broker, tmp_path, profile=None):
    profile = profile or _profile()
    state = StateStore(str(tmp_path / "s.db"))
    risk = RiskManager(profile, state.load_risk_state())
    return Orchestrator(profile=profile, data=data, broker=broker, state=state,
                        risk=risk, journal=TradeJournal())


def _dip_and_recover():
    base = list(np.linspace(100, 130, 80)); dip = list(np.linspace(130, 118, 6))
    return _series(base + dip)  # ends oversold/below vwap, regime neutral with ma=50


def test_tick_opens_position_on_signal(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker(equity=1000.0)
    orch = _orch(data, broker, tmp_path)
    orch.tick(now=T0)
    assert len(broker.buys) == 1                 # entered
    assert orch.state.load_position() is not None  # persisted

def test_tick_no_entry_when_flat_and_no_signal(tmp_path):
    df = _series(list(np.linspace(100, 130, 90)))  # clean uptrend, not oversold
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker()
    orch = _orch(data, broker, tmp_path)
    orch.tick(now=T0)
    assert broker.buys == []

def test_tick_exits_on_stop(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker(equity=1000.0)
    orch = _orch(data, broker, tmp_path)
    orch.tick(now=T0)                              # opens
    pos = orch.state.load_position()
    assert pos is not None
    data.set_price(pos.stop * 0.99)               # price drops below stop
    orch.tick(now=T0 + timedelta(minutes=1))
    assert len(broker.sells) == 1                  # exited via market sell
    assert orch.state.load_position() is None
    assert len(orch.journal.trades) == 1
    assert orch.journal.trades[0].exit_reason == ExitReason.STOP

def test_tick_blocked_by_killswitch(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=float(df["close"].iloc[-1]))
    broker = FakeBroker()
    state = StateStore(str(tmp_path / "s.db"))
    rs = RiskState(kill_switch_active=True, kill_switch_reason="test")
    state.save_risk_state(rs)
    risk = RiskManager(_profile(), state.load_risk_state())
    orch = Orchestrator(profile=_profile(), data=data, broker=broker, state=state,
                        risk=risk, journal=TradeJournal())
    orch.tick(now=T0)
    assert broker.buys == []

def test_reconcile_adopts_broker_position_if_state_empty(tmp_path):
    df = _dip_and_recover()
    data = FakeData(df, price=110.0)
    broker = FakeBroker()
    broker.position = {"symbol": "TRX/USD", "qty": 50.0, "avg_entry_price": 100.0,
                       "market_value": 5500.0}
    orch = _orch(data, broker, tmp_path)
    orch.reconcile(now=T0)
    # broker says we hold but state was empty -> a position record now exists
    assert orch.state.load_position() is not None
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_orchestrator.py -v`
Expected: ModuleNotFoundError: `swingbot.orchestrator`.

- [ ] **Step 3: Implement `src/swingbot/orchestrator.py`**

```python
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

    # ---- startup reconciliation ----
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
            # broker has nothing but we thought we held -> clear stale record
            self.state.clear_position()

    # ---- one cycle ----
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

    def _maybe_enter(self, now: datetime, equity: float) -> None:
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

    # ---- run loop ----
    def run(self, max_iterations: int | None = None) -> None:
        self.reconcile(datetime.now(timezone.utc))
        count = 0
        while max_iterations is None or count < max_iterations:
            try:
                self.tick()
            except Exception as e:  # never let one bad tick kill the loop
                print(f"[orchestrator] tick error: {e}")
            count += 1
            time.sleep(self.profile.poll_seconds)

    # ---- helpers ----
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

    def _timeframe_minutes(self, tf: str) -> int:  # pragma: no cover - thin wrapper
        return _timeframe_minutes(tf)


def _timeframe_minutes(tf: str) -> int:
    unit = tf[-1]
    n = int(tf[:-1])
    return n * {"m": 1, "h": 60, "d": 1440}[unit]
```

- [ ] **Step 4: Run, confirm PASS**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_orchestrator.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run FULL suite**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest -q`
Expected: all pass; live Alpaca tests skipped. (~51 + 11 + 5 = ~67 passed, ~2 skipped.)

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator tick() + run loop with client-side exit management"
```

---

## Task 9: `swingbot-run` CLI entrypoint

**Files:**
- Create: `src/swingbot/run.py`
- Modify: `pyproject.toml` (add console script)
- Test: `tests/test_run_cli.py`

- [ ] **Step 1: Write the failing test** `tests/test_run_cli.py`

```python
import json

from swingbot.run import build_orchestrator


def test_build_orchestrator_wires_components(tmp_path, monkeypatch):
    # Avoid real network: stub the Alpaca adapters used by build_orchestrator.
    import swingbot.run as run_mod

    class _Data:
        def __init__(self, *a, **k): pass
    class _Broker:
        def __init__(self, *a, **k): pass

    monkeypatch.setattr(run_mod, "AlpacaData", _Data)
    monkeypatch.setattr(run_mod, "AlpacaBroker", _Broker)
    monkeypatch.setenv("ALPACA_API_KEY_ID", "kid")
    monkeypatch.setenv("ALPACA_API_SECRET_KEY", "sec")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    profile = {"symbol": "TRX/USD",
               "signals": {"oversold": {"weight": 1.0, "oversold_level": 45}},
               "entry_threshold": 0.2}
    pf = tmp_path / "p.json"
    pf.write_text(json.dumps(profile))

    orch = build_orchestrator(str(pf), db_path=str(tmp_path / "s.db"))
    assert orch.profile.symbol == "TRX/USD"
    assert orch.broker is not None
    assert orch.data is not None
```

- [ ] **Step 2: Run, confirm FAIL**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_run_cli.py -v`
Expected: ModuleNotFoundError: `swingbot.run`.

- [ ] **Step 3: Implement `src/swingbot/run.py`**

```python
from __future__ import annotations

import argparse
import json

from swingbot.broker.alpaca import AlpacaBroker
from swingbot.config import load_alpaca_credentials, load_dotenv
from swingbot.data.alpaca import AlpacaData
from swingbot.journal import TradeJournal
from swingbot.orchestrator import Orchestrator
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager
from swingbot.state import StateStore


def build_orchestrator(profile_path: str, db_path: str = "swingbot.db") -> Orchestrator:
    load_dotenv()
    creds = load_alpaca_credentials()
    with open(profile_path) as f:
        profile = StrategyProfile.from_dict(json.load(f))
    data = AlpacaData(creds.key_id, creds.secret_key)
    broker = AlpacaBroker(creds.key_id, creds.secret_key, paper=creds.paper)
    state = StateStore(db_path)
    risk = RiskManager(profile, state.load_risk_state())
    return Orchestrator(profile=profile, data=data, broker=broker, state=state,
                        risk=risk, journal=TradeJournal())


def main() -> None:
    ap = argparse.ArgumentParser(description="swingbot live/paper runner")
    ap.add_argument("--profile", required=True, help="strategy profile JSON path")
    ap.add_argument("--db", default="swingbot.db", help="SQLite state DB path")
    args = ap.parse_args()
    orch = build_orchestrator(args.profile, db_path=args.db)
    creds = load_alpaca_credentials()
    mode = "PAPER" if creds.paper else "LIVE"
    print(f"[swingbot] starting in {mode} mode for {orch.profile.symbol}")
    orch.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add console script to `pyproject.toml`**

In the existing `[project.scripts]` block add a second line so it reads:
```toml
[project.scripts]
swingbot-backtest = "swingbot.cli:main"
swingbot-run = "swingbot.run:main"
```
Reinstall:
```bash
cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pip install -e ".[dev]" -q
```

- [ ] **Step 5: Run, confirm PASS**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest tests/test_run_cli.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/run.py pyproject.toml tests/test_run_cli.py
git commit -m "feat: swingbot-run CLI entrypoint (paper/live orchestrator)"
```

---

## Final verification

- [ ] **Run the entire suite**

Run: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pytest -q`
Expected: all tests pass; the Alpaca live tests show as SKIPPED (no creds in env). Report counts.

- [ ] **Optional live smoke (manual, requires real paper creds in `.env`)**

```bash
cd /home/redji/crypto-swing-bot && . .venv/bin/activate
# export creds from .env into this shell so the gated tests run:
export $(grep -v '^#' .env | xargs)
pytest tests/test_alpaca_data.py tests/test_alpaca_broker.py -v   # live smoke
# then a real paper run (Ctrl-C to stop):
swingbot-run --profile profiles/trx.json --db swingbot.db
```
(You'll create `profiles/trx.json` with your tuned parameters; it follows the same schema as the backtest profile JSON.)

---

## What Phase 2 delivers

A runnable paper/live trading bot: Alpaca crypto market data + broker adapters behind the Phase 1 protocols, a pure `RiskManager` enforcing all four circuit breakers with fixed-fractional sizing, a SQLite `StateStore` that survives restarts and reconciles against the broker, client-side exit management (the only correct approach for Alpaca crypto), and an always-on orchestrator driven by `swingbot-run --profile ...`. Every Phase 1 strategy module is reused unchanged, and the exit rule is shared verbatim between backtest and live.

**Phase 3 (separate plan) will add:** the FastAPI control API + websocket and the Valhalla-styled React dashboard, reading the StateStore/journal/metrics and driving the orchestrator's controls (halt/resume/mode/flatten) with the spec's guardrails.
