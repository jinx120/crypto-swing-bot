# Phase 1 — Backend Concurrency Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the backend that trades several symbols concurrently — a single-thread `PortfolioSupervisor` that ticks one `Orchestrator` per armed strategy under a shared-capital `PortfolioRiskManager`, reading all market data from a warm cache. Paper-only; no HTTP yet (that's Phase 2).

**Architecture:** Single supervisor loop, sequential per-strategy ticks, single-writer portfolio risk accounting (no locks on the money path). Per-symbol state, an armed-profile set, batched/cached data so API calls scale with timeframes not symbols. The existing `Orchestrator`, `RiskManager`, `SimulatedBroker`, and signal/confluence engine are reused unchanged except for two small optional hooks on `Orchestrator`.

**Tech Stack:** Python 3.11+, pandas, SQLite, alpaca-py. Tests with pytest (`pythonpath=["src"]`, fakes per existing `tests/` patterns). Run all tests with `.venv/bin/python -m pytest -q`.

**Reference:** Design spec `docs/superpowers/specs/2026-05-31-multi-asset-concurrent-trading-design.md` §4, §5, §6.

---

### Task 1: PortfolioRiskManager (the single-writer portfolio gate)

**Files:**
- Create: `src/swingbot/portfolio_risk.py`
- Test: `tests/test_portfolio_risk.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_portfolio_risk.py`:

```python
from datetime import datetime, timedelta, timezone

from swingbot.portfolio_risk import (
    PortfolioRiskManager, PortfolioRiskState, PortfolioSettings,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _mgr(**kw):
    settings = PortfolioSettings(
        max_concurrent=kw.pop("max_concurrent", 3),
        max_total_deployed_frac=kw.pop("max_total_deployed_frac", 0.8),
        portfolio_daily_loss_limit_pct=kw.pop("portfolio_daily_loss_limit_pct", 0.08),
    )
    return PortfolioRiskManager(settings, PortfolioRiskState(**kw))


def test_approves_when_clean():
    m = _mgr(day_start_equity=1000.0)
    d = m.check_can_enter(equity=1000.0, open_position_count=0,
                          deployed_value=0.0, prospective_value=100.0)
    assert d.approved is True


def test_blocks_on_max_concurrent():
    m = _mgr(max_concurrent=2)
    d = m.check_can_enter(equity=1000.0, open_position_count=2,
                          deployed_value=0.0, prospective_value=10.0)
    assert d.approved is False and "concurrent" in d.reason.lower()


def test_blocks_when_deployed_cap_would_break():
    m = _mgr(max_total_deployed_frac=0.5)            # cap = 500
    d = m.check_can_enter(equity=1000.0, open_position_count=1,
                          deployed_value=450.0, prospective_value=100.0)  # 550 > 500
    assert d.approved is False and "deployed" in d.reason.lower()


def test_allows_up_to_deployed_cap():
    m = _mgr(max_total_deployed_frac=0.5)            # cap = 500
    d = m.check_can_enter(equity=1000.0, open_position_count=1,
                          deployed_value=400.0, prospective_value=100.0)  # 500 == cap
    assert d.approved is True


def test_blocks_when_kill_switch_active():
    m = _mgr(kill_switch_active=True, kill_switch_reason="x")
    d = m.check_can_enter(equity=1000.0, open_position_count=0,
                          deployed_value=0.0, prospective_value=10.0)
    assert d.approved is False and "kill" in d.reason.lower()


def test_daily_loss_trips_kill_switch():
    m = _mgr(day="2026-01-01", day_start_equity=1000.0,
             realized_pnl_today=-70.0, portfolio_daily_loss_limit_pct=0.08)  # limit -80
    m.on_trade_closed(-15.0, now=T0)                  # total -85 <= -80
    assert m.state.kill_switch_active is True


def test_start_day_resets_counters():
    m = _mgr(day="2026-01-01", realized_pnl_today=-50.0, day_start_equity=1000.0)
    m.start_day(now=T0 + timedelta(days=1), equity=900.0)
    assert m.state.day == "2026-01-02"
    assert m.state.realized_pnl_today == 0.0
    assert m.state.day_start_equity == 900.0
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_portfolio_risk.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.portfolio_risk'`.

- [ ] **Step 3: Implement the module**

Create `src/swingbot/portfolio_risk.py`:

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_portfolio_risk.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/portfolio_risk.py tests/test_portfolio_risk.py
git commit -m "feat(risk): add PortfolioRiskManager with concurrent/deployed/daily-loss caps"
```

---

### Task 2: Per-strategy keyed StateStore + portfolio state + migration

Extend `StateStore` so positions and risk state are keyed by a strategy string (default
`"default"`, so existing single-strategy callers and tests are unchanged), add a portfolio
risk-state row, `load_all_positions()`, and a `StrategyStateView` that binds one key and
exposes the no-arg interface the `Orchestrator` already calls.

**Files:**
- Modify (full rewrite): `src/swingbot/state.py`
- Test: `tests/test_state_multi.py` (new); existing `tests/test_state.py` must still pass.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_state_multi.py`:

```python
from datetime import datetime, timezone

from swingbot.state import StateStore, StrategyStateView
from swingbot.portfolio_risk import PortfolioRiskState
from swingbot.types import OpenPosition, Regime, Side


def _pos(symbol, now):
    return OpenPosition(symbol=symbol, entry_ts=now, entry_price=0.1, qty=10.0,
                        stop=0.09, tp=0.12, max_hold_until=now,
                        score_at_entry=0.5, regime_at_entry=Regime.UPTREND, side=Side.LONG)


def test_positions_are_keyed_by_strategy(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    s.save_position(_pos("BTC/USD", now), strategy="btc")
    s.save_position(_pos("ETH/USD", now), strategy="eth")
    assert s.load_position("btc").symbol == "BTC/USD"
    assert s.load_position("eth").symbol == "ETH/USD"
    assert set(s.load_all_positions()) == {"btc", "eth"}
    s.clear_position("btc")
    assert s.load_position("btc") is None
    assert set(s.load_all_positions()) == {"eth"}


def test_portfolio_risk_state_roundtrip(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    s.save_portfolio_risk_state(PortfolioRiskState(
        kill_switch_active=True, kill_switch_reason="cap", day="2026-01-01",
        realized_pnl_today=-12.0, day_start_equity=1000.0))
    out = s.load_portfolio_risk_state()
    assert out.kill_switch_active is True and out.realized_pnl_today == -12.0


def test_strategy_state_view_binds_key(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    view = StrategyStateView(s, "btc")
    view.save_position(_pos("BTC/USD", now))           # no-arg interface
    assert view.load_position().symbol == "BTC/USD"
    assert s.load_position("btc").symbol == "BTC/USD"   # written under the bound key
    view.clear_position()
    assert view.load_position() is None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_state_multi.py -q`
Expected: FAIL — `ImportError: cannot import name 'StrategyStateView'`.

- [ ] **Step 3: Rewrite `src/swingbot/state.py`**

Replace the entire contents of `src/swingbot/state.py` with:

```python
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from swingbot.portfolio_risk import PortfolioRiskState
from swingbot.risk import RiskState
from swingbot.types import OpenPosition, Regime, Side

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
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS positions (strategy TEXT PRIMARY KEY, data TEXT)")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS risk_states (strategy TEXT PRIMARY KEY, data TEXT)")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS portfolio_risk (id INTEGER PRIMARY KEY, data TEXT)")
        self._conn.commit()
        self._migrate_legacy()

    def _migrate_legacy(self) -> None:
        """Move any legacy single-row position/risk_state (id=1) into the keyed
        tables under the default key, once."""
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
        self._conn.commit()

    # --- positions (keyed) ---
    def save_position(self, pos: OpenPosition, strategy: str = _DEFAULT) -> None:
        payload = {
            "symbol": pos.symbol, "entry_ts": pos.entry_ts.isoformat(),
            "entry_price": pos.entry_price, "qty": pos.qty, "stop": pos.stop, "tp": pos.tp,
            "max_hold_until": pos.max_hold_until.isoformat(),
            "score_at_entry": pos.score_at_entry,
            "regime_at_entry": pos.regime_at_entry.value, "side": pos.side.value,
        }
        self._conn.execute(
            "INSERT OR REPLACE INTO positions (strategy, data) VALUES (?, ?)",
            (strategy, json.dumps(payload)))
        self._conn.commit()

    def load_position(self, strategy: str = _DEFAULT) -> OpenPosition | None:
        row = self._conn.execute(
            "SELECT data FROM positions WHERE strategy=?", (strategy,)).fetchone()
        return self._pos_from_json(row[0]) if row else None

    def clear_position(self, strategy: str = _DEFAULT) -> None:
        self._conn.execute("DELETE FROM positions WHERE strategy=?", (strategy,))
        self._conn.commit()

    def load_all_positions(self) -> dict[str, OpenPosition]:
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
            side=Side(d["side"]))

    # --- per-strategy risk state (keyed) ---
    def save_risk_state(self, rs: RiskState, strategy: str = _DEFAULT) -> None:
        payload = {
            "kill_switch_active": rs.kill_switch_active,
            "kill_switch_reason": rs.kill_switch_reason, "day": rs.day,
            "realized_pnl_today": rs.realized_pnl_today,
            "consecutive_losses": rs.consecutive_losses,
            "day_start_equity": rs.day_start_equity, "cooldown_until": rs.cooldown_until,
        }
        self._conn.execute(
            "INSERT OR REPLACE INTO risk_states (strategy, data) VALUES (?, ?)",
            (strategy, json.dumps(payload)))
        self._conn.commit()

    def load_risk_state(self, strategy: str = _DEFAULT) -> RiskState:
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
        self._conn.execute(
            "INSERT OR REPLACE INTO portfolio_risk (id, data) VALUES (1, ?)",
            (json.dumps(payload),))
        self._conn.commit()

    def load_portfolio_risk_state(self) -> PortfolioRiskState:
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

    def save_risk_state(self, rs: RiskState) -> None:
        self._store.save_risk_state(rs, self._key)

    def load_risk_state(self) -> RiskState:
        return self._store.load_risk_state(self._key)
```

- [ ] **Step 4: Run new + existing state tests**

Run: `.venv/bin/python -m pytest tests/test_state_multi.py tests/test_state.py tests/test_state_threading.py -q`
Expected: PASS (existing single-strategy tests still pass via the default key; new keyed tests pass).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/state.py tests/test_state_multi.py
git commit -m "feat(state): per-strategy keyed positions/risk + portfolio risk row + legacy migration"
```

---

### Task 3: ProfileStore armed set + live-eligible flag + portfolio settings

**Files:**
- Modify: `src/swingbot/profiles.py`
- Test: `tests/test_profiles_armed.py` (new); existing `tests/test_profiles.py` must still pass.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_profiles_armed.py`:

```python
import pytest
from swingbot.profiles import ProfileStore


def _p(symbol="TRX/USD"):
    return {"symbol": symbol, "signals": {"oversold": {"weight": 1.0}}, "entry_threshold": 0.3}


def test_arm_disarm_and_list(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    s.save("btc", _p("BTC/USD")); s.save("eth", _p("ETH/USD"))
    assert s.list_armed() == []
    s.arm("btc"); s.arm("eth")
    assert set(s.list_armed()) == {"btc", "eth"}
    assert s.is_armed("btc") is True
    s.disarm("btc")
    assert s.list_armed() == ["eth"]


def test_arm_unknown_raises(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    with pytest.raises(ValueError):
        s.arm("nope")


def test_live_eligible_flag(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    s.save("btc", _p("BTC/USD")); s.arm("btc")
    assert s.is_live_eligible("btc") is False
    s.set_live_eligible("btc", True)
    assert s.is_live_eligible("btc") is True
    flags = {f["name"]: f["live_eligible"] for f in s.armed_with_flags()}
    assert flags == {"btc": True}


def test_active_migrates_into_armed(tmp_path):
    path = str(tmp_path / "p.db")
    s = ProfileStore(path)
    s.save("btc", _p("BTC/USD")); s.set_active("btc")
    # reopen: migration seeds armed from the legacy active pointer
    s2 = ProfileStore(path)
    assert "btc" in s2.list_armed()


def test_portfolio_settings_defaults_and_override(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    d = s.get_portfolio_settings()
    assert d["max_concurrent"] == 5 and d["max_total_deployed_frac"] == 0.80
    s.set_portfolio_settings({"max_concurrent": 8})
    assert s.get_portfolio_settings()["max_concurrent"] == 8
    assert s.get_portfolio_settings()["max_total_deployed_frac"] == 0.80  # unchanged keys persist
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_profiles_armed.py -q`
Expected: FAIL — `AttributeError: 'ProfileStore' object has no attribute 'arm'`.

- [ ] **Step 3: Extend `ProfileStore`**

In `src/swingbot/profiles.py`, add the `armed` table creation and migration to `__init__`,
then append the new methods. In `__init__`, after the existing
`self._conn.execute("CREATE TABLE IF NOT EXISTS meta ...")` line and before
`self._conn.commit()`, insert:

```python
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS armed "
            "(name TEXT PRIMARY KEY, live_eligible INTEGER DEFAULT 0)")
```

Then, after `self._conn.commit()` at the end of `__init__`, add:

```python
        self._migrate_active_to_armed()
```

Add these methods to the class (after `get_active`):

```python
    # --- armed set + per-strategy live-eligible flag ---
    def arm(self, name: str) -> None:
        if self.get(name) is None:
            raise ValueError(f"unknown profile {name!r}")
        self._conn.execute(
            "INSERT OR IGNORE INTO armed (name, live_eligible) VALUES (?, 0)", (name,))
        self._conn.commit()

    def disarm(self, name: str) -> None:
        self._conn.execute("DELETE FROM armed WHERE name=?", (name,))
        self._conn.commit()

    def list_armed(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM armed ORDER BY name").fetchall()
        return [r[0] for r in rows]

    def is_armed(self, name: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM armed WHERE name=?", (name,)).fetchone() is not None

    def set_live_eligible(self, name: str, eligible: bool) -> None:
        if not self.is_armed(name):
            raise ValueError(f"profile {name!r} is not armed")
        self._conn.execute(
            "UPDATE armed SET live_eligible=? WHERE name=?", (1 if eligible else 0, name))
        self._conn.commit()

    def is_live_eligible(self, name: str) -> bool:
        row = self._conn.execute(
            "SELECT live_eligible FROM armed WHERE name=?", (name,)).fetchone()
        return bool(row[0]) if row else False

    def armed_with_flags(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT name, live_eligible FROM armed ORDER BY name").fetchall()
        return [{"name": n, "live_eligible": bool(le)} for n, le in rows]

    def _migrate_active_to_armed(self) -> None:
        if self.list_armed():
            return
        active = self.get_active_name()
        if active and self.get(active) is not None:
            self.arm(active)

    # --- portfolio settings (stored in meta as JSON) ---
    _PORTFOLIO_DEFAULTS = {
        "max_concurrent": 5,
        "max_total_deployed_frac": 0.80,
        "portfolio_daily_loss_limit_pct": 0.08,
    }

    def get_portfolio_settings(self) -> dict:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key='portfolio_settings'").fetchone()
        out = dict(self._PORTFOLIO_DEFAULTS)
        if row:
            out.update(json.loads(row[0]))
        return out

    def set_portfolio_settings(self, settings: dict) -> None:
        allowed = set(self._PORTFOLIO_DEFAULTS)
        bad = set(settings) - allowed
        if bad:
            raise ValueError(f"unknown portfolio settings: {sorted(bad)}")
        merged = self.get_portfolio_settings()
        merged.update(settings)
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('portfolio_settings', ?)",
            (json.dumps(merged),))
        self._conn.commit()
```

- [ ] **Step 4: Run new + existing profile tests**

Run: `.venv/bin/python -m pytest tests/test_profiles_armed.py tests/test_profiles.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/profiles.py tests/test_profiles_armed.py
git commit -m "feat(profiles): armed set, live-eligible flag, portfolio settings, active->armed migration"
```

---

### Task 4: Multi-symbol Alpaca data + MarketData.refresh_many

Batch fetching so API calls scale with timeframes, not symbols.

**Files:**
- Modify: `src/swingbot/data/alpaca.py`
- Modify: `src/swingbot/data/market.py`
- Test: `tests/test_market_multi.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_market_multi.py`:

```python
from datetime import datetime, timezone

import pandas as pd

from swingbot.data.market import MarketData
from swingbot.data.store import CandleStore


def _df(prices, start=None):
    start = start or datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows = []
    for i, p in enumerate(prices):
        ts = pd.Timestamp(start) + pd.Timedelta(minutes=15 * i)
        rows.append({"ts": ts, "open": p, "high": p + 1, "low": p - 1,
                     "close": p + 0.5, "volume": 100 + i})
    return pd.DataFrame(rows)


class _FakeMultiProvider:
    def __init__(self, dfs):
        self.dfs = dfs            # {symbol: df}
        self.multi_calls = 0
    def get_candles_multi(self, symbols, timeframe, lookback):
        self.multi_calls += 1
        return {s: self.dfs[s] for s in symbols if s in self.dfs}


def test_refresh_many_upserts_each_symbol(tmp_path, monkeypatch):
    store = CandleStore(str(tmp_path / "c.db"))
    md = MarketData(store, creds=None)
    prov = _FakeMultiProvider({"BTC/USD": _df([10, 11, 12]), "ETH/USD": _df([20, 21])})
    monkeypatch.setattr(md, "_provider", lambda: prov)

    n = md.refresh_many(["BTC/USD", "ETH/USD"], "15m")
    assert prov.multi_calls == 1          # one batched fetch
    assert n == 5                          # 3 + 2 bars upserted
    assert len(store.get("BTC/USD", "15m")) == 3
    assert len(store.get("ETH/USD", "15m")) == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_market_multi.py -q`
Expected: FAIL — `AttributeError: 'MarketData' object has no attribute 'refresh_many'`.

- [ ] **Step 3a: Add multi-symbol methods to AlpacaData**

In `src/swingbot/data/alpaca.py`, add these two methods to the `AlpacaData` class (after
`get_latest_price`):

```python
    def get_candles_multi(self, symbols, timeframe: str, lookback: int) -> dict:
        """One batched bars request for many symbols. Returns {symbol: DataFrame}."""
        tf = parse_timeframe(timeframe)
        start = datetime.now(timezone.utc) - timedelta(days=fetch_window_days(timeframe, lookback))
        req = CryptoBarsRequest(symbol_or_symbols=list(symbols), timeframe=tf, start=start)
        bars = self._client.get_crypto_bars(req)
        out = {}
        for sym in symbols:
            records = []
            try:
                series = bars[sym]
            except (KeyError, TypeError):
                series = []
            for bar in series:
                records.append({
                    "timestamp": bar.timestamp, "open": bar.open, "high": bar.high,
                    "low": bar.low, "close": bar.close, "volume": bar.volume})
            if records:
                out[sym] = bars_to_df(records).tail(lookback).reset_index(drop=True)
        return out

    def get_latest_prices(self, symbols) -> dict:
        """One batched latest-trade request for many symbols. Returns {symbol: price}."""
        req = CryptoLatestTradeRequest(symbol_or_symbols=list(symbols))
        trades = self._client.get_crypto_latest_trade(req)
        out = {}
        for sym in symbols:
            try:
                out[sym] = float(trades[sym].price)
            except (KeyError, TypeError):
                continue
        return out
```

- [ ] **Step 3b: Add refresh_many to MarketData**

In `src/swingbot/data/market.py`, add this method to the `MarketData` class (after
`refresh`):

```python
    def refresh_many(self, symbols, timeframe: str, lookback: int | None = None) -> int:
        """Batched fetch for many symbols at one timeframe; upsert each into the store."""
        prov = self._provider()
        if not prov:
            return 0
        dfs = prov.get_candles_multi(symbols, timeframe, lookback or self.default_lookback)
        return sum(self.store.upsert_df(sym, timeframe, df) for sym, df in dfs.items())
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_market_multi.py tests/test_market.py tests/test_alpaca_data.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/data/alpaca.py src/swingbot/data/market.py tests/test_market_multi.py
git commit -m "feat(data): batched multi-symbol fetch (get_candles_multi/get_latest_prices, refresh_many)"
```

---

### Task 5: Orchestrator portfolio-gate hooks

Two optional, backward-compatible hooks: a pre-entry portfolio gate and a post-close
notifier. Defaults `None` keep single-strategy behavior identical.

**Files:**
- Modify: `src/swingbot/orchestrator.py`
- Test: `tests/test_orchestrator_portfolio.py` (new); existing orchestrator tests must pass.

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator_portfolio.py`:

```python
from datetime import datetime, timedelta, timezone
import numpy as np, pandas as pd

from swingbot.orchestrator import Orchestrator
from swingbot.portfolio_risk import PortfolioDecision
from swingbot.profile import StrategyProfile
from swingbot.risk import RiskManager
from swingbot.state import StateStore
from swingbot.journal import TradeJournal

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _series(closes):
    closes = np.array(closes, dtype=float); n = len(closes)
    return pd.DataFrame({"ts": pd.date_range(end=T0, periods=n, freq="15min", tz="UTC"),
                         "open": closes, "high": closes * 1.002, "low": closes * 0.998,
                         "close": closes, "volume": np.full(n, 100.0)})


class FakeData:
    def __init__(self, c, p): self._c = c; self._p = p
    def get_candles(self, *a, **k): return self._c
    def get_latest_price(self, *a, **k): return self._p


class FakeBroker:
    def __init__(self): self.position = None; self.buys = []; self.sells = []
    def get_account(self): return {"equity": 1000.0, "cash": 1000.0, "buying_power": 1000.0}
    def get_position(self, s): return self.position
    def submit_market_buy(self, s, q):
        self.position = {"symbol": s, "qty": q, "avg_entry_price": 100.0, "market_value": q * 100}
        self.buys.append((s, q)); return "b"
    def submit_market_sell(self, s, q): self.position = None; self.sells.append((s, q)); return "s"
    def cancel_all(self): pass


def _profile():
    return StrategyProfile.from_dict({"symbol": "TRX/USD", "timeframe": "15m",
        "signals": {"oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
                    "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05}},
        "entry_threshold": 0.25, "regime_ma_period": 50, "atr_period": 14,
        "stop_atr_mult": 2.0, "take_profit_atr_mult": 2.0, "max_hold_bars": 32, "risk_per_trade": 0.02})


def _dip():
    return _series(list(np.linspace(100, 130, 80)) + list(np.linspace(130, 118, 6)))


def test_portfolio_gate_blocks_entry(tmp_path):
    df = _dip(); data = FakeData(df, float(df["close"].iloc[-1])); broker = FakeBroker()
    p = _profile(); st = StateStore(str(tmp_path / "s.db"))
    seen = {}
    def gate(symbol, value):
        seen["symbol"] = symbol; seen["value"] = value
        return PortfolioDecision(False, "blocked")
    orch = Orchestrator(profile=p, data=data, broker=broker, state=st,
                        risk=RiskManager(p, st.load_risk_state()), journal=TradeJournal(),
                        portfolio_gate=gate)
    orch.tick(now=T0)
    assert broker.buys == []                       # gate vetoed the entry
    assert seen["symbol"] == "TRX/USD" and seen["value"] > 0


def test_portfolio_gate_allows_and_notifies_on_close(tmp_path):
    df = _dip(); data = FakeData(df, float(df["close"].iloc[-1])); broker = FakeBroker()
    p = _profile(); st = StateStore(str(tmp_path / "s.db"))
    closed = []
    orch = Orchestrator(profile=p, data=data, broker=broker, state=st,
                        risk=RiskManager(p, st.load_risk_state()), journal=TradeJournal(),
                        portfolio_gate=lambda s, v: PortfolioDecision(True),
                        portfolio_on_close=lambda pnl, now: closed.append(pnl))
    orch.tick(now=T0)
    assert len(broker.buys) == 1
    pos = orch.state.load_position()
    data._p = pos.stop * 0.99                       # force a stop-out
    orch.tick(now=T0 + timedelta(minutes=1))
    assert len(closed) == 1                          # portfolio_on_close fired with the pnl
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_orchestrator_portfolio.py -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'portfolio_gate'`.

- [ ] **Step 3: Add the hooks to Orchestrator**

In `src/swingbot/orchestrator.py`:

(a) Change the `__init__` signature and body. Replace:

```python
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
```

with:

```python
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
        self.portfolio_gate = portfolio_gate          # (symbol, value) -> decision with .approved
        self.portfolio_on_close = portfolio_on_close  # (pnl, now) -> None
```

(b) In `_maybe_enter`, gate the entry. Replace:

```python
        qty = self.risk.size(equity=equity, entry_price=price, stop_price=stop)
        if qty <= 0:
            return
        self.broker.submit_market_buy(self.profile.symbol, qty)
```

with:

```python
        qty = self.risk.size(equity=equity, entry_price=price, stop_price=stop)
        if qty <= 0:
            return
        if self.portfolio_gate is not None:
            decision = self.portfolio_gate(self.profile.symbol, qty * price)
            if not decision.approved:
                return
        self.broker.submit_market_buy(self.profile.symbol, qty)
```

(c) In `_manage_open`, notify on close. Replace:

```python
        self.journal.record(trade)
        self.risk.on_trade_closed(trade, now=now)
        self.state.clear_position()
        self.state.save_risk_state(self.risk.state)

    def flatten(self, now: datetime | None = None) -> None:
```

with:

```python
        self.journal.record(trade)
        self.risk.on_trade_closed(trade, now=now)
        if self.portfolio_on_close is not None:
            self.portfolio_on_close(trade.pnl, now)
        self.state.clear_position()
        self.state.save_risk_state(self.risk.state)

    def flatten(self, now: datetime | None = None) -> None:
```

(d) In `flatten`, notify on close. Replace:

```python
        self.journal.record(trade)
        self.risk.on_trade_closed(trade, now=now)
        self.state.clear_position()
        self.state.save_risk_state(self.risk.state)

    def _maybe_enter(self, now: datetime, equity: float) -> None:
```

with:

```python
        self.journal.record(trade)
        self.risk.on_trade_closed(trade, now=now)
        if self.portfolio_on_close is not None:
            self.portfolio_on_close(trade.pnl, now)
        self.state.clear_position()
        self.state.save_risk_state(self.risk.state)

    def _maybe_enter(self, now: datetime, equity: float) -> None:
```

- [ ] **Step 4: Run new + existing orchestrator tests**

Run: `.venv/bin/python -m pytest tests/test_orchestrator_portfolio.py tests/test_orchestrator.py tests/test_orchestrator_control.py -q`
Expected: PASS (existing tests unaffected — hooks default to `None`).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/orchestrator.py tests/test_orchestrator_portfolio.py
git commit -m "feat(orchestrator): optional portfolio gate + post-close hooks"
```

---

### Task 6: PortfolioSupervisor + CachedProvider (the integrator)

Ties everything together: builds one `Orchestrator` per armed profile sharing a cached data
provider, a single `AlpacaBroker`, a keyed `StateStore`, and one `PortfolioRiskManager`;
warms all symbols with batched fetches; ticks strategies sorted by name; caches per-strategy
snapshots + a portfolio summary for the API.

**Files:**
- Create: `src/swingbot/supervisor.py`
- Test: `tests/test_supervisor.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_supervisor.py`:

```python
from datetime import datetime, timezone
import numpy as np, pandas as pd

from swingbot.supervisor import PortfolioSupervisor, CachedProvider, _bars_to_df
from swingbot.data.store import CandleStore
from swingbot.profiles import ProfileStore

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _bars(symbol_base=100.0, n=120):
    base = list(np.linspace(symbol_base, symbol_base * 1.3, n - 6))
    dip = list(np.linspace(symbol_base * 1.3, symbol_base * 1.18, 6))
    closes = base + dip
    t0 = 1_700_000_000
    return [{"time": t0 + i * 900, "open": c, "high": c * 1.002, "low": c * 0.998,
             "close": c, "volume": 100.0} for i, c in enumerate(closes)]


class FakeMarket:
    """Stands in for MarketData: serves preloaded bars, records refresh calls."""
    def __init__(self, bars_by_symbol):
        self.bars = bars_by_symbol
        self.refresh_calls = []
    def get(self, symbol, timeframe, limit=500, max_age=None):
        return self.bars.get(symbol, [])[-limit:]
    def refresh_many(self, symbols, timeframe, lookback=None):
        self.refresh_calls.append((tuple(sorted(symbols)), timeframe)); return 0
    def _provider(self):
        return None


class FakeBroker:
    def __init__(self): self.positions = {}; self.buys = []; self.sells = []
    def get_account(self): return {"equity": 1000.0, "cash": 1000.0, "buying_power": 1000.0}
    def get_position(self, s): return self.positions.get(s)
    def submit_market_buy(self, s, q):
        self.positions[s] = {"symbol": s, "qty": q, "avg_entry_price": 100.0, "market_value": q * 100}
        self.buys.append((s, q)); return "b"
    def submit_market_sell(self, s, q): self.positions.pop(s, None); self.sells.append((s, q)); return "s"
    def cancel_all(self): pass


def _profile(symbol):
    return {"symbol": symbol, "timeframe": "15m",
            "signals": {"oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
                        "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05}},
            "entry_threshold": 0.25, "regime_ma_period": 50, "atr_period": 14,
            "stop_atr_mult": 2.0, "take_profit_atr_mult": 2.0, "max_hold_bars": 32,
            "risk_per_trade": 0.02}


def _supervisor(tmp_path, symbols):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    for sym in symbols:
        name = sym.split("/")[0].lower()
        profiles.save(name, _profile(sym)); profiles.arm(name)
    market = FakeMarket({sym: _bars(100.0 + i * 10) for i, sym in enumerate(symbols)})
    broker = FakeBroker()
    sup = PortfolioSupervisor(profiles=profiles, creds=None,
                              state_db=str(tmp_path / "s.db"), market=market,
                              broker=broker, mode="paper")
    sup.build()
    return sup, broker, market


def test_bars_to_df_shape():
    df = _bars_to_df(_bars(100.0, 5))
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert str(df["ts"].dt.tz) == "UTC"


def test_supervisor_ticks_all_armed_and_warms_once(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.tick_all(now=T0)
    # one batched warm per timeframe (both symbols share 15m)
    assert market.refresh_calls == [(("BTC/USD", "ETH/USD"), "15m")]
    # both armed strategies were evaluated and (given the dip) opened positions
    assert set(broker.positions) == {"BTC/USD", "ETH/USD"}


def test_supervisor_status_lists_strategies(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.tick_all(now=T0)
    st = sup.status()
    assert "portfolio" in st and isinstance(st["strategies"], list)
    names = {s["name"] for s in st["strategies"]}
    assert names == {"btc", "eth"}
    assert st["portfolio"]["open_positions"] == 2


def test_max_concurrent_caps_open_positions(tmp_path):
    sup, broker, market = _supervisor(tmp_path, ["BTC/USD", "ETH/USD"])
    sup.profiles.set_portfolio_settings({"max_concurrent": 1})
    sup.build()                                   # rebuild with new settings
    sup.tick_all(now=T0)
    assert len(broker.positions) == 1             # portfolio cap allowed only one entry
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.supervisor'`.

- [ ] **Step 3: Implement the supervisor**

Create `src/swingbot/supervisor.py`:

```python
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

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
from swingbot.state import StateStore, StrategyStateView
from swingbot.types import MarketContext

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


class PortfolioSupervisor:
    """Runs one Orchestrator per armed strategy in a single loop under a shared
    PortfolioRiskManager. The only component that talks to the broker/data upstream."""

    def __init__(self, profiles: ProfileStore, creds, state_db: str,
                 market: MarketData | None = None, broker=None, mode: str = "paper"):
        self.profiles = profiles
        self.creds = creds
        self.state_db = state_db
        self.market = market
        self.mode = mode
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

    # ---- construction ----
    def build(self) -> None:
        if self.market is None:
            from swingbot.data.store import CandleStore  # local import to keep tests light
            raise RuntimeError("market must be provided (webmain wires MarketData)")
        if self._broker is None:
            c = self.creds.get() if self.creds else None
            if c is None:
                raise RuntimeError("Alpaca credentials not set")
            self._broker = AlpacaBroker(c.key_id, c.secret_key, paper=(self.mode == "paper"))

        self._store = StateStore(self.state_db)
        settings = PortfolioSettings(**self.profiles.get_portfolio_settings())
        self._portfolio_risk = PortfolioRiskManager(
            settings, self._store.load_portfolio_risk_state())

        provider = CachedProvider(self.market, self._latest_prices, self._timeframes)
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
    def status(self) -> dict:
        strategies = []
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
        return {"portfolio": self._summary or {"mode": self.mode, "running": self._running},
                "strategies": strategies}

    # ---- lifecycle ----
    def start(self) -> None:
        if self._running:
            return
        self.build()
        for s in self._strategies.values():
            s["orch"].reconcile(datetime.now(timezone.utc))
        self._running = True

        def loop():
            while self._running:
                try:
                    self.tick_all()
                except Exception as e:
                    print(f"[supervisor] cycle error: {e}")
                time.sleep(self._poll_seconds())

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def pause(self) -> None:
        self.paused = True

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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_supervisor.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full suite (no regressions)**

Run: `.venv/bin/python -m pytest -q`
Expected: all prior tests still pass plus the new ones (the 160-baseline grows; nothing red).

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor.py
git commit -m "feat(supervisor): PortfolioSupervisor + CachedProvider — concurrent paper trading core"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** §4.2 supervisor (Task 6), §4.3 portfolio risk (Task 1), §4.4 entry
  flow (Tasks 5+6 gate), §5 state/profile model + migration (Tasks 2+3), §6 batched data
  (Task 4 + supervisor `_warm`). Live-eligibility *enforcement* is surfaced in `status` here
  but **enforced** in Phase 4; the supervisor currently trades all armed strategies in
  paper mode, which is correct for a paper-only Phase 1.
- **Type consistency:** `PortfolioDecision.approved`, `check_can_enter(...)` keyword args,
  `StrategyStateView` no-arg methods, and `CachedProvider.get_candles/get_latest_price` are
  used identically across tasks.
- **No direct Alpaca calls from orchestrators:** they receive `CachedProvider`; only the
  supervisor's `_warm` touches the upstream (via `MarketData.refresh_many` and the
  provider's `get_latest_prices`).
- The supervisor is wired into the web app and `webmain` in **Phase 2**; Phase 1 leaves
  `service.py`/`webmain.py` untouched so the current single-strategy app keeps working.
