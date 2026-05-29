# Phase 3A — Backend Control & Config API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A localhost FastAPI backend that lets the (Phase 3B) web UI fully run the bot — manage strategy profiles, enter Alpaca credentials, monitor live state, and control the bot (halt/resume/flatten/mode) — with no hand-edited files.

**Architecture:** FastAPI app bound to 127.0.0.1. Profiles live in SQLite (`ProfileStore`); the Alpaca secret lives in a chmod-600 gitignored JSON file (`CredentialStore`). A `BotService` runs the Phase 2 `Orchestrator` in a background thread and exposes control + a live status snapshot; the API is a thin layer over a `BotController` protocol (real `BotService` in prod, a fake in tests). Write endpoints require a shared token loaded from the data dir; reads are open (localhost only). Tests use FastAPI `TestClient` with fakes — fully offline.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx (TestClient), stdlib sqlite3/json/threading. Reuses all Phase 1/2 modules unchanged.

---

## Security invariants (enforced in code, verified by tests where possible)
- Server binds **127.0.0.1 only** (the `swingbot-web` entry passes host="127.0.0.1").
- **Write endpoints require `X-Token` header** equal to a token stored in the data dir.
- The Alpaca **secret is never returned** by any endpoint (`/api/credentials` returns `has_secret: bool` only).
- Credential file is written with **mode 0o600** and lives under a gitignored data dir.
- **Go-live is gated server-side** by `graduation.can_go_live(...)`; the client cannot bypass it.

---

## File Structure
```
src/swingbot/
  profiles.py        # CREATE: ProfileStore (SQLite CRUD + active pointer)
  credentials.py     # CREATE: CredentialStore (chmod-600 JSON file)
  snapshot.py        # CREATE: signal_snapshot() pure display function
  graduation.py      # CREATE: can_go_live(metrics, min_trades, min_expectancy)
  service.py         # CREATE: BotController protocol + BotService (threaded orchestrator)
  web.py             # CREATE: create_app(...) FastAPI app + auth dep + routes
  webmain.py         # CREATE: swingbot-web entry (uvicorn 127.0.0.1, token bootstrap)
  orchestrator.py    # MODIFY: add `paused` flag + flatten() method
pyproject.toml       # MODIFY: add fastapi/uvicorn deps, httpx dev dep, swingbot-web script
tests/
  test_profiles.py test_credentials.py test_snapshot.py test_graduation.py
  test_web_read.py test_web_profiles.py test_web_credentials.py test_web_control.py
```

---

## Task 1: Dependencies + ProfileStore

**Files:** Modify `pyproject.toml`; Create `src/swingbot/profiles.py`; Test `tests/test_profiles.py`

- [ ] **Step 1: Update `pyproject.toml`**

Set dependencies and dev extras:
```toml
dependencies = ["pandas>=2.0", "numpy>=1.24", "alpaca-py>=0.20", "fastapi>=0.110", "uvicorn>=0.29"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "httpx>=0.27"]
```
Then: `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && pip install -e ".[dev]" -q` (must succeed).

- [ ] **Step 2: Write failing test `tests/test_profiles.py`**

```python
import pytest
from swingbot.profiles import ProfileStore


def _p(symbol="TRX/USD", thr=0.3):
    return {"symbol": symbol,
            "signals": {"oversold": {"weight": 1.0, "oversold_level": 45}},
            "entry_threshold": thr}


def test_save_get_list_delete(tmp_path):
    s = ProfileStore(str(tmp_path / "db.sqlite"))
    assert s.list() == []
    s.save("trx", _p())
    assert s.list() == ["trx"]
    assert s.get("trx")["symbol"] == "TRX/USD"
    s.delete("trx")
    assert s.list() == []
    assert s.get("trx") is None


def test_active_pointer(tmp_path):
    s = ProfileStore(str(tmp_path / "db.sqlite"))
    assert s.get_active_name() is None
    s.save("trx", _p())
    s.set_active("trx")
    assert s.get_active_name() == "trx"
    assert s.get_active()["symbol"] == "TRX/USD"


def test_save_rejects_invalid_profile(tmp_path):
    s = ProfileStore(str(tmp_path / "db.sqlite"))
    with pytest.raises(ValueError):
        s.save("bad", {"signals": {}})  # missing required 'symbol'


def test_set_active_unknown_raises(tmp_path):
    s = ProfileStore(str(tmp_path / "db.sqlite"))
    with pytest.raises(ValueError):
        s.set_active("nope")
```

- [ ] **Step 3: Run, confirm FAIL** — `pytest tests/test_profiles.py -v` (ModuleNotFoundError).

- [ ] **Step 4: Implement `src/swingbot/profiles.py`**

```python
from __future__ import annotations

import json
import sqlite3

from swingbot.profile import StrategyProfile


class ProfileStore:
    """SQLite-backed strategy profiles + an 'active' pointer."""

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS profiles (name TEXT PRIMARY KEY, data TEXT)"
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        self._conn.commit()

    def save(self, name: str, profile: dict) -> None:
        StrategyProfile.from_dict(profile)  # validate; raises ValueError if bad
        self._conn.execute(
            "INSERT OR REPLACE INTO profiles (name, data) VALUES (?, ?)",
            (name, json.dumps(profile)),
        )
        self._conn.commit()

    def get(self, name: str) -> dict | None:
        row = self._conn.execute(
            "SELECT data FROM profiles WHERE name=?", (name,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self) -> list[str]:
        rows = self._conn.execute("SELECT name FROM profiles ORDER BY name").fetchall()
        return [r[0] for r in rows]

    def delete(self, name: str) -> None:
        self._conn.execute("DELETE FROM profiles WHERE name=?", (name,))
        self._conn.commit()

    def set_active(self, name: str) -> None:
        if self.get(name) is None:
            raise ValueError(f"unknown profile {name!r}")
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('active', ?)", (name,)
        )
        self._conn.commit()

    def get_active_name(self) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key='active'").fetchone()
        return row[0] if row else None

    def get_active(self) -> dict | None:
        name = self.get_active_name()
        return self.get(name) if name else None
```

- [ ] **Step 5: Run, confirm PASS** (4 passed). Then full suite `pytest -q` (~88 passed, 2 skipped).
- [ ] **Step 6: Commit** — `git add pyproject.toml src/swingbot/profiles.py tests/test_profiles.py && git commit -m "feat: ProfileStore (SQLite profiles + active pointer) + web deps"`

---

## Task 2: CredentialStore

**Files:** Create `src/swingbot/credentials.py`; Test `tests/test_credentials.py`

- [ ] **Step 1: Write failing test `tests/test_credentials.py`**

```python
import os
import stat
from swingbot.credentials import CredentialStore


def test_set_and_status_hides_secret(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    assert c.status() == {"key_id": None, "has_secret": False, "paper": True}
    c.set("KID", "SECRET", "https://paper-api.alpaca.markets")
    st = c.status()
    assert st["key_id"] == "KID"
    assert st["has_secret"] is True
    assert st["paper"] is True
    assert "SECRET" not in str(st)  # secret never surfaced


def test_file_is_chmod_600(tmp_path):
    path = tmp_path / "creds.json"
    CredentialStore(str(path)).set("KID", "SECRET", "https://paper-api.alpaca.markets")
    mode = stat.S_IMODE(os.stat(path).st_mode)
    assert mode == 0o600


def test_get_returns_full_credentials(tmp_path):
    c = CredentialStore(str(tmp_path / "creds.json"))
    c.set("KID", "SECRET", "https://api.alpaca.markets")  # live URL
    full = c.get()
    assert full.key_id == "KID" and full.secret_key == "SECRET"
    assert full.paper is False


def test_get_none_when_unset(tmp_path):
    assert CredentialStore(str(tmp_path / "creds.json")).get() is None
```

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Implement `src/swingbot/credentials.py`**

```python
from __future__ import annotations

import json
import os

from swingbot.config import AlpacaCredentials


class CredentialStore:
    """Alpaca credentials in a chmod-600 local JSON file. Secret is never exposed
    via status(); only get() (server-internal) returns it."""

    def __init__(self, path: str):
        self.path = path

    def set(self, key_id: str, secret_key: str, base_url: str) -> None:
        payload = {"key_id": key_id, "secret_key": secret_key, "base_url": base_url}
        # write then lock perms to owner-only
        with open(self.path, "w") as f:
            json.dump(payload, f)
        os.chmod(self.path, 0o600)

    def _load(self) -> dict | None:
        if not os.path.exists(self.path):
            return None
        with open(self.path) as f:
            return json.load(f)

    def status(self) -> dict:
        d = self._load()
        if not d:
            return {"key_id": None, "has_secret": False, "paper": True}
        return {
            "key_id": d.get("key_id"),
            "has_secret": bool(d.get("secret_key")),
            "paper": "paper" in d.get("base_url", "paper"),
        }

    def get(self) -> AlpacaCredentials | None:
        d = self._load()
        if not d or not d.get("key_id") or not d.get("secret_key"):
            return None
        base_url = d.get("base_url", "https://paper-api.alpaca.markets")
        return AlpacaCredentials(key_id=d["key_id"], secret_key=d["secret_key"],
                                 base_url=base_url, paper="paper" in base_url)
```

- [ ] **Step 4: Run, confirm PASS** (4 passed). Full suite green.
- [ ] **Step 5: Commit** — `git add src/swingbot/credentials.py tests/test_credentials.py && git commit -m "feat: CredentialStore (chmod-600 file, secret never exposed)"`

---

## Task 3: signal_snapshot (live display)

**Files:** Create `src/swingbot/snapshot.py`; Test `tests/test_snapshot.py`

- [ ] **Step 1: Write failing test `tests/test_snapshot.py`**

```python
import numpy as np
import pandas as pd
from swingbot.profile import StrategyProfile
from swingbot.snapshot import signal_snapshot
from swingbot.types import MarketContext


def _series(closes):
    closes = np.array(closes, dtype=float); n = len(closes)
    return pd.DataFrame({"ts": pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"),
                         "open": closes, "high": closes * 1.002, "low": closes * 0.998,
                         "close": closes, "volume": np.full(n, 100.0)})


def _profile():
    return StrategyProfile.from_dict({"symbol": "TRX/USD",
        "signals": {"oversold": {"weight": 0.6, "oversold_level": 45, "period": 14},
                    "vwap": {"weight": 0.4, "window": 20, "max_dist": 0.05}},
        "entry_threshold": 0.25, "regime_ma_period": 50})


def test_snapshot_shape():
    df = _series(list(np.linspace(100, 130, 80)) + list(np.linspace(130, 118, 6)))
    snap = signal_snapshot(_profile(), MarketContext(candles=df))
    assert set(snap.keys()) >= {"regime", "permitted", "score", "threshold", "passed", "contributions", "signals"}
    assert set(snap["contributions"]) == {"oversold", "vwap"}
    assert snap["threshold"] == 0.25
    assert isinstance(snap["passed"], bool)
    assert abs(snap["score"] - sum(snap["contributions"].values())) < 1e-9
```

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Implement `src/swingbot/snapshot.py`**

```python
from __future__ import annotations

from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.profile import StrategyProfile
from swingbot.regime import RegimeFilter
from swingbot.types import MarketContext


def signal_snapshot(profile: StrategyProfile, ctx: MarketContext) -> dict:
    """Compute the current regime + confluence breakdown for DISPLAY only.
    Does not trade. Mirrors the orchestrator's entry evaluation."""
    regime = RegimeFilter(profile)
    reg = regime.evaluate(ctx)
    conf = ConfluenceEngine(build_signals(profile), profile).evaluate(ctx)
    return {
        "regime": reg.regime.value,
        "permitted": regime.permits_entry(reg.regime),
        "score": conf.score,
        "threshold": conf.threshold,
        "passed": conf.passed,
        "contributions": conf.contributions,
        "signals": {name: {"score": r.score, "meta": r.meta}
                    for name, r in conf.signals.items()},
    }
```

- [ ] **Step 4: Run, confirm PASS.** Full suite green.
- [ ] **Step 5: Commit** — `git add src/swingbot/snapshot.py tests/test_snapshot.py && git commit -m "feat: signal_snapshot for live UI display"`

---

## Task 4: Graduation gate

**Files:** Create `src/swingbot/graduation.py`; Test `tests/test_graduation.py`

- [ ] **Step 1: Write failing test `tests/test_graduation.py`**

```python
from swingbot.graduation import can_go_live
from swingbot.metrics import Metrics


def _m(n, expectancy, max_dd=-0.02):
    return Metrics(n_trades=n, win_rate=0.5, avg_win=2, avg_loss=-1,
                   expectancy=expectancy, profit_factor=1.5, max_drawdown=max_dd)


def test_blocked_when_too_few_trades():
    ok, reason = can_go_live(_m(5, 1.0), min_trades=30, min_expectancy=0.0)
    assert ok is False and "trades" in reason.lower()


def test_blocked_when_negative_expectancy():
    ok, reason = can_go_live(_m(40, -0.5), min_trades=30, min_expectancy=0.0)
    assert ok is False and "expectancy" in reason.lower()


def test_allowed_when_criteria_met():
    ok, reason = can_go_live(_m(40, 0.8), min_trades=30, min_expectancy=0.0)
    assert ok is True
```

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Implement `src/swingbot/graduation.py`**

```python
from __future__ import annotations

from swingbot.metrics import Metrics


def can_go_live(metrics: Metrics, min_trades: int = 30,
                min_expectancy: float = 0.0) -> tuple[bool, str]:
    """Server-side gate: paper results must clear these bars before LIVE."""
    if metrics.n_trades < min_trades:
        return (False, f"need >= {min_trades} paper trades (have {metrics.n_trades})")
    if metrics.expectancy <= min_expectancy:
        return (False, f"expectancy {metrics.expectancy:.4f} must exceed {min_expectancy}")
    return (True, "ok")
```

- [ ] **Step 4: Run, confirm PASS.** Full suite green.
- [ ] **Step 5: Commit** — `git add src/swingbot/graduation.py tests/test_graduation.py && git commit -m "feat: server-side graduation gate for go-live"`

---

## Task 5: Orchestrator control hooks (paused + flatten)

**Files:** Modify `src/swingbot/orchestrator.py`; Test `tests/test_orchestrator_control.py`

- [ ] **Step 1: Write failing test `tests/test_orchestrator_control.py`**

```python
from datetime import datetime, timedelta, timezone
import numpy as np, pandas as pd
from swingbot.orchestrator import Orchestrator
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
    def __init__(self, c, p): self._c=c; self._p=p
    def set_price(self,p): self._p=p
    def get_candles(self,*a,**k): return self._c
    def get_latest_price(self,*a,**k): return self._p


class FakeBroker:
    def __init__(self): self.position=None; self.buys=[]; self.sells=[]
    def get_account(self): return {"equity":1000.0,"cash":1000.0,"buying_power":1000.0}
    def get_position(self,s): return self.position
    def submit_market_buy(self,s,q): self.position={"symbol":s,"qty":q,"avg_entry_price":100.0,"market_value":q*100}; self.buys.append((s,q)); return "b"
    def submit_market_sell(self,s,q): self.position=None; self.sells.append((s,q)); return "s"
    def cancel_all(self): pass


def _profile():
    return StrategyProfile.from_dict({"symbol":"TRX/USD","timeframe":"15m",
        "signals":{"oversold":{"weight":0.6,"oversold_level":45,"period":14},
                   "vwap":{"weight":0.4,"window":20,"max_dist":0.05}},
        "entry_threshold":0.25,"regime_ma_period":50,"atr_period":14,
        "stop_atr_mult":2.0,"take_profit_atr_mult":2.0,"max_hold_bars":32,"risk_per_trade":0.02})


def _orch(data, broker, tmp_path):
    p=_profile(); st=StateStore(str(tmp_path/"s.db"))
    return Orchestrator(profile=p,data=data,broker=broker,state=st,
                        risk=RiskManager(p,st.load_risk_state()),journal=TradeJournal())


def _dip():
    return _series(list(np.linspace(100,130,80))+list(np.linspace(130,118,6)))


def test_paused_blocks_new_entries(tmp_path):
    data=FakeData(_dip(), float(_dip()["close"].iloc[-1])); broker=FakeBroker()
    orch=_orch(data,broker,tmp_path); orch.paused=True
    orch.tick(now=T0)
    assert broker.buys == []


def test_flatten_closes_open_position(tmp_path):
    data=FakeData(_dip(), float(_dip()["close"].iloc[-1])); broker=FakeBroker()
    orch=_orch(data,broker,tmp_path)
    orch.tick(now=T0)                       # opens
    assert orch.state.load_position() is not None
    orch.flatten(now=T0 + timedelta(minutes=1))
    assert len(broker.sells) == 1
    assert orch.state.load_position() is None
    assert len(orch.journal.trades) == 1
```

- [ ] **Step 2: Run, confirm FAIL** (`paused` attr / `flatten` missing).

- [ ] **Step 3: Modify `src/swingbot/orchestrator.py`**

In `__init__`, add at the end of the method body:
```python
        self.paused = False
```
In `_maybe_enter`, add as the FIRST statement (before the existing broker-holds guard):
```python
        if self.paused:
            return
```
Add a `flatten` method (place it right after `_manage_open`):
```python
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
```

- [ ] **Step 4: Run new test + FULL suite.** All pass (existing orchestrator tests unchanged). If any regress, STOP and report.
- [ ] **Step 5: Commit** — `git add src/swingbot/orchestrator.py tests/test_orchestrator_control.py && git commit -m "feat: orchestrator pause flag + flatten() control hook"`

---

## Task 6: BotController protocol + BotService

**Files:** Create `src/swingbot/service.py`; Test `tests/test_service.py`

`BotService` runs the orchestrator in a thread and exposes control + a status snapshot. The threaded/network behavior is hard to unit-test, so this task tests only the **pure status assembly** via a constructor that accepts injected components; the API layer (later tasks) is tested against a `FakeBotController` defined in those tests.

- [ ] **Step 1: Write failing test `tests/test_service.py`**

```python
from swingbot.service import BotController


def test_botcontroller_protocol_methods_exist():
    # Protocol documents the surface the API depends on.
    for m in ("status", "journal", "metrics", "halt", "reset", "pause",
              "resume", "flatten", "set_mode", "start", "stop"):
        assert hasattr(BotController, m)
```

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Implement `src/swingbot/service.py`**

```python
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
    """Runs the Orchestrator in a background thread; exposes control + status.
    `mode` is 'paper' or 'live'. Adapters are rebuilt on start()."""

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
        snap = None
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
```

- [ ] **Step 4: Run, confirm PASS.** Full suite green.
- [ ] **Step 5: Commit** — `git add src/swingbot/service.py tests/test_service.py && git commit -m "feat: BotController protocol + threaded BotService"`

---

## Task 7: FastAPI app — auth + read endpoints

**Files:** Create `src/swingbot/web.py`; Test `tests/test_web_read.py`

`create_app` takes injected `controller`, `profiles`, `creds`, and a `token`, so tests use fakes. Write endpoints require header `X-Token`.

- [ ] **Step 1: Write failing test `tests/test_web_read.py`**

```python
from fastapi.testclient import TestClient
from swingbot.web import create_app


class FakeController:
    def status(self): return {"mode": "paper", "running": True, "paused": False}
    def journal(self): return [{"pnl": 1.0}]
    def metrics(self): return {"n_trades": 1, "expectancy": 1.0}
    def halt(self): self.halted = True
    def reset(self): pass
    def pause(self): pass
    def resume(self): pass
    def flatten(self): pass
    def set_mode(self, mode): return (True, f"mode set to {mode}")
    def start(self): pass
    def stop(self): pass


def _client(token="tok"):
    app = create_app(controller=FakeController(), profiles=None, creds=None, token=token)
    return TestClient(app)


def test_state_ok():
    r = _client().get("/api/state")
    assert r.status_code == 200 and r.json()["mode"] == "paper"

def test_journal_and_metrics():
    c = _client()
    assert c.get("/api/journal").json() == [{"pnl": 1.0}]
    assert c.get("/api/metrics").json()["n_trades"] == 1

def test_write_requires_token():
    c = _client(token="secret")
    assert c.post("/api/control/halt").status_code == 401         # no token
    assert c.post("/api/control/halt", headers={"X-Token": "wrong"}).status_code == 401
    assert c.post("/api/control/halt", headers={"X-Token": "secret"}).status_code == 200
```

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Implement `src/swingbot/web.py`** (read endpoints + auth + a control/halt stub used by the token test; remaining control endpoints land in Task 9)

```python
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException


def create_app(controller, profiles, creds, token: str) -> FastAPI:
    app = FastAPI(title="swingbot")

    def require_token(x_token: str | None = Header(default=None)):
        if x_token != token:
            raise HTTPException(status_code=401, detail="bad or missing token")

    @app.get("/api/state")
    def state():
        return controller.status()

    @app.get("/api/journal")
    def journal():
        return controller.journal()

    @app.get("/api/metrics")
    def metrics():
        return controller.metrics()

    @app.post("/api/control/halt")
    def halt(_=Depends(require_token)):
        controller.halt()
        return {"ok": True}

    # store references for later route modules / tests
    app.state.controller = controller
    app.state.profiles = profiles
    app.state.creds = creds
    app.state.token = token
    return app
```

- [ ] **Step 4: Run, confirm PASS** (3 passed). Full suite green.
- [ ] **Step 5: Commit** — `git add src/swingbot/web.py tests/test_web_read.py && git commit -m "feat: FastAPI app with auth token + read endpoints"`

---

## Task 8: FastAPI — profile + credential endpoints

**Files:** Modify `src/swingbot/web.py`; Test `tests/test_web_profiles.py`, `tests/test_web_credentials.py`

- [ ] **Step 1: Write failing tests**

`tests/test_web_profiles.py`:
```python
from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.profiles import ProfileStore


class FakeController:
    def status(self): return {}
    def journal(self): return []
    def metrics(self): return {}
    def halt(self): pass
    def reset(self): pass
    def pause(self): pass
    def resume(self): pass
    def flatten(self): pass
    def set_mode(self, m): return (True, "")
    def start(self): pass
    def stop(self): pass


def _client(tmp_path, token="tok"):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    app = create_app(controller=FakeController(), profiles=profiles, creds=None, token=token)
    return TestClient(app), profiles


def test_profile_crud_and_active(tmp_path):
    c, _ = _client(tmp_path)
    h = {"X-Token": "tok"}
    body = {"name": "trx", "profile": {"symbol": "TRX/USD",
            "signals": {"oversold": {"weight": 1.0}}, "entry_threshold": 0.3}}
    assert c.post("/api/profiles", json=body, headers=h).status_code == 200
    assert "trx" in c.get("/api/profiles").json()
    assert c.post("/api/profiles/active", json={"name": "trx"}, headers=h).status_code == 200
    assert c.get("/api/profiles/active").json()["name"] == "trx"

def test_profile_create_requires_token(tmp_path):
    c, _ = _client(tmp_path)
    body = {"name": "x", "profile": {"symbol": "TRX/USD", "signals": {}}}
    assert c.post("/api/profiles", json=body).status_code == 401

def test_invalid_profile_rejected(tmp_path):
    c, _ = _client(tmp_path)
    body = {"name": "bad", "profile": {"signals": {}}}  # no symbol
    assert c.post("/api/profiles", json=body, headers={"X-Token": "tok"}).status_code == 400
```

`tests/test_web_credentials.py`:
```python
from fastapi.testclient import TestClient
from swingbot.web import create_app
from swingbot.credentials import CredentialStore
from test_web_profiles import FakeController  # reuse


def _client(tmp_path, token="tok"):
    creds = CredentialStore(str(tmp_path / "creds.json"))
    app = create_app(controller=FakeController(), profiles=None, creds=creds, token=token)
    return TestClient(app), creds


def test_credentials_status_and_set(tmp_path):
    c, _ = _client(tmp_path)
    assert c.get("/api/credentials").json()["has_secret"] is False
    r = c.put("/api/credentials", headers={"X-Token": "tok"},
              json={"key_id": "KID", "secret_key": "SEC",
                    "base_url": "https://paper-api.alpaca.markets"})
    assert r.status_code == 200
    st = c.get("/api/credentials").json()
    assert st["key_id"] == "KID" and st["has_secret"] is True
    assert "SEC" not in r.text  # secret never echoed

def test_set_credentials_requires_token(tmp_path):
    c, _ = _client(tmp_path)
    assert c.put("/api/credentials", json={"key_id": "K", "secret_key": "S",
                 "base_url": "x"}).status_code == 401
```

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Add endpoints to `src/swingbot/web.py`** (inside `create_app`, before the `app.state...` lines)

```python
    from pydantic import BaseModel

    class ProfileBody(BaseModel):
        name: str
        profile: dict

    class ActiveBody(BaseModel):
        name: str

    class CredBody(BaseModel):
        key_id: str
        secret_key: str
        base_url: str = "https://paper-api.alpaca.markets"

    @app.get("/api/profiles")
    def list_profiles():
        return profiles.list()

    @app.post("/api/profiles")
    def save_profile(body: ProfileBody, _=Depends(require_token)):
        try:
            profiles.save(body.name, body.profile)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.get("/api/profiles/active")
    def active_profile():
        return {"name": profiles.get_active_name(), "profile": profiles.get_active()}

    @app.post("/api/profiles/active")
    def set_active(body: ActiveBody, _=Depends(require_token)):
        try:
            profiles.set_active(body.name)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.delete("/api/profiles/{name}")
    def delete_profile(name: str, _=Depends(require_token)):
        profiles.delete(name)
        return {"ok": True}

    @app.get("/api/credentials")
    def cred_status():
        return creds.status()

    @app.put("/api/credentials")
    def set_creds(body: CredBody, _=Depends(require_token)):
        creds.set(body.key_id, body.secret_key, body.base_url)
        return {"ok": True}
```

- [ ] **Step 4: Run both new test files + FULL suite.** All pass.
- [ ] **Step 5: Commit** — `git add src/swingbot/web.py tests/test_web_profiles.py tests/test_web_credentials.py && git commit -m "feat: profile + credential API endpoints"`

---

## Task 9: FastAPI — control endpoints + swingbot-web entry

**Files:** Modify `src/swingbot/web.py`, `pyproject.toml`; Create `src/swingbot/webmain.py`; Test `tests/test_web_control.py`

- [ ] **Step 1: Write failing test `tests/test_web_control.py`**

```python
from fastapi.testclient import TestClient
from swingbot.web import create_app


class RecordingController:
    def __init__(self): self.calls = []
    def status(self): return {}
    def journal(self): return []
    def metrics(self): return {}
    def halt(self): self.calls.append("halt")
    def reset(self): self.calls.append("reset")
    def pause(self): self.calls.append("pause")
    def resume(self): self.calls.append("resume")
    def flatten(self): self.calls.append("flatten")
    def set_mode(self, mode): self.calls.append(("mode", mode)); return (mode == "paper", "live blocked" if mode == "live" else "ok")
    def start(self): pass
    def stop(self): pass


def _client():
    ctrl = RecordingController()
    return TestClient(create_app(controller=ctrl, profiles=None, creds=None, token="t")), ctrl


def test_control_actions_invoke_controller():
    c, ctrl = _client(); h = {"X-Token": "t"}
    for action in ("reset", "pause", "resume", "flatten"):
        assert c.post(f"/api/control/{action}", headers=h).status_code == 200
    assert {"reset", "pause", "resume", "flatten"} <= set(ctrl.calls)

def test_mode_switch_returns_gate_result():
    c, _ = _client(); h = {"X-Token": "t"}
    assert c.post("/api/control/mode", json={"mode": "paper"}, headers=h).json()["ok"] is True
    r = c.post("/api/control/mode", json={"mode": "live"}, headers=h)
    assert r.json()["ok"] is False and "blocked" in r.json()["reason"]

def test_control_requires_token():
    c, _ = _client()
    assert c.post("/api/control/pause").status_code == 401
```

- [ ] **Step 2: Run, confirm FAIL.**

- [ ] **Step 3: Add control endpoints to `src/swingbot/web.py`** (inside `create_app`, before `app.state...`)

```python
    class ModeBody(BaseModel):
        mode: str

    @app.post("/api/control/reset")
    def control_reset(_=Depends(require_token)):
        controller.reset(); return {"ok": True}

    @app.post("/api/control/pause")
    def control_pause(_=Depends(require_token)):
        controller.pause(); return {"ok": True}

    @app.post("/api/control/resume")
    def control_resume(_=Depends(require_token)):
        controller.resume(); return {"ok": True}

    @app.post("/api/control/flatten")
    def control_flatten(_=Depends(require_token)):
        controller.flatten(); return {"ok": True}

    @app.post("/api/control/mode")
    def control_mode(body: ModeBody, _=Depends(require_token)):
        ok, reason = controller.set_mode(body.mode)
        return {"ok": ok, "reason": reason}
```
(The `/api/control/halt` route already exists from Task 7.)

- [ ] **Step 4: Implement `src/swingbot/webmain.py`** (real wiring + token bootstrap, 127.0.0.1)

```python
from __future__ import annotations

import os
import secrets

import uvicorn

from swingbot.credentials import CredentialStore
from swingbot.profiles import ProfileStore
from swingbot.service import BotService
from swingbot.web import create_app

DATA_DIR = os.path.expanduser("~/.swingbot")


def _ensure_token(path: str) -> str:
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    tok = secrets.token_urlsafe(24)
    with open(path, "w") as f:
        f.write(tok)
    os.chmod(path, 0o600)
    return tok


def main() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    token = _ensure_token(os.path.join(DATA_DIR, "token"))
    profiles = ProfileStore(os.path.join(DATA_DIR, "swingbot.db"))
    creds = CredentialStore(os.path.join(DATA_DIR, "credentials.json"))
    service = BotService(profiles=profiles, creds=creds,
                         state_db=os.path.join(DATA_DIR, "swingbot.db"))
    app = create_app(controller=service, profiles=profiles, creds=creds, token=token)
    print(f"[swingbot-web] token: {token}")
    print("[swingbot-web] http://127.0.0.1:8000  (localhost only)")
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Add script to `pyproject.toml`** `[project.scripts]`:
```toml
swingbot-web = "swingbot.webmain:main"
```
Reinstall: `pip install -e ".[dev]" -q`.

- [ ] **Step 6: Run new test + FULL suite.** All pass. Confirm `swingbot-web` import: `python -c "import swingbot.webmain"`.
- [ ] **Step 7: Commit** — `git add src/swingbot/web.py src/swingbot/webmain.py pyproject.toml tests/test_web_control.py && git commit -m "feat: control endpoints + swingbot-web entry (127.0.0.1 + token)"`

---

## Final verification
- [ ] `pytest -q` — all pass, 2 Alpaca tests skipped. Report counts.
- [ ] `python -c "import swingbot.web, swingbot.webmain, swingbot.service"` exits 0.
- [ ] Gitignore check: confirm `~/.swingbot/` data dir is outside the repo (it is — under home), and that no credential/token files are tracked: `git status --porcelain` clean.

## What Phase 3A delivers
A localhost FastAPI backend exposing read (state/journal/metrics), config (profiles CRUD + active, credentials set/status with the secret never returned), and control (halt/reset/pause/resume/flatten/mode with server-side go-live gating) endpoints — all token-guarded on writes — plus a `BotService` that runs the Phase 2 orchestrator in a background thread and a `swingbot-web` entrypoint bound to 127.0.0.1. Phase 3B builds the React Valhalla dashboard against this API.
