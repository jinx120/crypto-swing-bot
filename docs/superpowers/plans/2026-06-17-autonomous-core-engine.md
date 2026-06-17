# Autonomous Core Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a bulletproof, fully autonomous paper BTC/USD trade-execution engine as an isolated side-folder experiment that decides + acts every 5 minutes with zero user input and records every outcome to a durable journal readable via `report`.

**Architecture:** A single synchronous tick loop runs a fixed pipeline (data → reconcile → exits → decide → risk → execute → journal) every 5 minutes, every stage wrapped so no failure kills the loop. The decision layer is a **pure function**. The engine lives in its own package (`core_engine`) under `lab/core-engine/`, on a dedicated `core-engine` git branch, and **imports** the proven v1 `swingbot` libraries (broker, risk, exits, candle store, Kronos/confluence/regime signals, runtime-state) rather than copying them. `master` and `src/swingbot/` are untouched.

**Tech Stack:** Python 3.11+, pytest, SQLite, pandas, Alpaca paper (via `swingbot.broker.alpaca`), Kronos (via `swingbot.signals.kronos_forecast`), Docker.

## Global Constraints

- **Isolation:** All new code lives under `lab/core-engine/`. Never modify `src/swingbot/` or anything on `master`. Work happens on branch `core-engine` (Claude integrates) / `codex/core-engine` (Codex develops, see §Collaboration). `master` stays clean until the experiment is proven.
- **Reuse by import, not copy:** Import proven plumbing from the installed `swingbot` package. Do not duplicate `swingbot` source into `core_engine`.
- **Single instrument:** `SYMBOL = "BTC/USD"` (USD-funded — never USDT). One position at a time. Long-only / spot only.
- **Timeframe:** `TIMEFRAME = "5Min"`, decide every 5 minutes. No deep-history archive dependency.
- **Cut entirely:** no self-improvement, no drift/usage-agent, no selftest health-check machinery, no UI. (Do not import `swingbot.selftest`, `swingbot.supervisor`, `swingbot.orchestrator`, `swingbot.discovery`, `swingbot.graduation`, `swingbot.strategy_search`, `swingbot.web*`, `swingbot.decision.ollama/prompt/proposals`.)
- **Truthfulness over optimism:** never report success on a partial failure. An order still `pending_new` is reported as such, not as filled. Unreadable state is reported unknown, never defaulted.
- **The loop never dies:** every stage is wrapped; a stage failure is journaled with its reason and the tick is skipped, not fatal.
- **TDD always:** failing test → run-it-fails → minimal impl → run-it-passes → commit. Frequent commits.

---

## File Structure (locked decomposition)

```
lab/core-engine/
  pyproject.toml                 # package `core_engine`; depends on local `swingbot` (editable)
  README.md                      # what this experiment is + how to run
  Dockerfile                     # headless engine image
  src/core_engine/
    __init__.py
    config.py                    # SYMBOL, TIMEFRAME, interval, the one StrategyProfile, db paths
    contracts.py                 # Action, Decision, OrderIntent, JournalEvent, EnginePosition
    market.py                    # build swingbot MarketContext from a candle window
    brain.py                     # PURE decide(window, position, *, profile, kronos) -> Decision
    risk_gate.py                 # Decision + account -> OrderIntent | veto (wraps swingbot RiskManager)
    journal.py                   # EngineJournal (SQLite append-only) + report()
    executor.py                  # OrderIntent -> place/track/reconcile; exit via market sell
    loop.py                      # tick() orchestrator + scheduler + auto-resume
    __main__.py                  # CLI: run | report | backtest
    backtest.py                  # shared decide->risk->exit path over historical bars
  tests/
    conftest.py                  # fakes: FakeBroker (pending_new), FakeKronos, fixture candle windows
    test_contracts.py
    test_brain.py
    test_risk_gate.py
    test_journal.py
    test_market.py
    test_executor.py
    test_loop.py
    test_backtest.py
```

**Ownership (see §Collaboration at end):** Codex owns the pure, fixture-testable modules (`contracts`, `brain`, `risk_gate`, `journal`, `backtest`). Claude owns the live-environment modules (`market`, `executor`, `loop`, `__main__`, Dockerfile) and all integration + live acceptance.

---

## Reused v1 symbols (import — do not reimplement)

These are the exact interfaces this plan relies on (verified in `src/swingbot/`):

- `swingbot.types`: `MarketContext(candles: pd.DataFrame, benchmark=None, htf=None)`, `Side`, `Regime`, `ExitReason`, `OrderStatus`, `ConfluenceResult(score, threshold, passed, contributions, signals)`, `RegimeResult(regime, meta)`, `SignalResult(name, score, meta)`.
- `swingbot.profile.StrategyProfile` — config object consumed by the brain + risk.
- `swingbot.regime.RegimeFilter(profile)` → `.evaluate(ctx) -> RegimeResult`, `.permits_entry(regime) -> bool`.
- `swingbot.confluence`: `build_signals(profile) -> list[Signal]`, `ConfluenceEngine(signals, profile).evaluate(ctx) -> ConfluenceResult`.
- `swingbot.signals.kronos_forecast.KronosForecastSignal(...)` → `.evaluate(ctx) -> SignalResult`.
- `swingbot.risk.RiskManager(profile, state)`: `.start_day(now, equity)`, `.check_can_enter(symbol, now, ...)-> RiskDecision`, `.size(equity, entry_price, stop_price) -> float`, `.on_trade_closed(trade, now)`; `RiskState`, `RiskDecision`.
- `swingbot.exits`: `bracket_levels(entry_price, atr, stop_mult, tp_mult) -> (stop, tp)`, `exit_decision(stop, tp, max_hold_until, high, low, close, now) -> (ExitReason, price) | None`.
- `swingbot.broker.base.Broker` (Protocol): `submit_market_buy(...)`, `submit_market_sell(...)`, `get_order(...)`, `get_position(symbol) -> dict|None`, `equity(mark_price) -> float`. Impls: `swingbot.broker.alpaca` (live paper), `swingbot.broker.simulated` (fake).
- `swingbot.data.store.CandleStore(path)`: `.upsert_df(symbol, timeframe, df)`, `.get(symbol, timeframe, limit) -> list[dict]`, `.coverage(symbol, timeframe) -> dict`.
- `swingbot.data.alpaca` — live 5-min candle fetch (used by `market.py` backfill/append).
- `swingbot.runtime_state.RuntimeStateStore(db_path)`: `.get_running_desired() -> bool`, `.set_running_desired(bool)`.

> When a task says "build a `MarketContext`", read `src/swingbot/types.py:123` for the exact `candles` DataFrame columns the v1 signals expect, and confirm against `src/swingbot/signals/ema_trend.py` (a simple consumer) before wiring.

---

## Phase 0 — Isolation scaffold + contracts (gates all parallel work)

### Task 1: Scaffold the isolated package + branch

**Files:**
- Create: `lab/core-engine/pyproject.toml`
- Create: `lab/core-engine/src/core_engine/__init__.py`
- Create: `lab/core-engine/tests/test_smoke.py`
- Create: `lab/core-engine/README.md`

**Interfaces:**
- Consumes: the local `swingbot` package (editable-installed in the same venv).
- Produces: an importable `core_engine` package and a working `pytest` run under `lab/core-engine/`.

- [x] **Step 1: Create the branch**

```bash
cd /home/redji/crypto-swing-bot
git checkout master && git checkout -b core-engine
```

- [x] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "core-engine"
version = "0.0.1"
description = "Isolated autonomous BTC/USD trade-execution engine (experiment)"
requires-python = ">=3.11"
dependencies = ["pandas", "swingbot"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [x] **Step 3: Write `src/core_engine/__init__.py`**

```python
"""Autonomous BTC/USD core engine — isolated experiment."""
__all__ = []
```

- [x] **Step 4: Write the smoke test `tests/test_smoke.py`**

```python
def test_package_imports():
    import core_engine  # noqa: F401


def test_swingbot_reuse_available():
    # The experiment reuses proven v1 plumbing by import.
    from swingbot.broker.base import Broker  # noqa: F401
    from swingbot.exits import exit_decision  # noqa: F401
```

- [x] **Step 5: Write `README.md`**

```markdown
# core-engine (experiment)

Isolated, headless autonomous trade-execution engine for **paper BTC/USD**, 5-min bars.
Lives on the `core-engine` branch; reuses the `swingbot` package by import. No UI.

Run:    `python -m core_engine run`
Report: `python -m core_engine report`
Backtest: `python -m core_engine backtest --from <iso> --to <iso>`
```

- [x] **Step 6: Install editable and run the smoke test**

Run: `cd lab/core-engine && pip install -e . && pytest tests/test_smoke.py -v`
Expected: 2 passed. (If `swingbot` is not importable, run `pip install -e ../..` first.)

- [x] **Step 7: Commit**

```bash
cd /home/redji/crypto-swing-bot
git add lab/core-engine
git commit -m "feat(core-engine): isolated package scaffold + branch"
```

---

### Task 2: Engine contracts + single-instrument config

**Files:**
- Create: `lab/core-engine/src/core_engine/contracts.py`
- Create: `lab/core-engine/src/core_engine/config.py`
- Test: `lab/core-engine/tests/test_contracts.py`

**Interfaces:**
- Produces (the contracts every other task consumes):
  - `Action` enum: `ENTER_LONG`, `HOLD`, `EXIT`.
  - `Decision(action: Action, confidence: float, reason: str, meta: dict)` — frozen.
  - `OrderIntent(symbol: str, qty: float, entry_price: float, stop: float, tp: float, max_hold_until: datetime, reason: str)` — frozen.
  - `EnginePosition(symbol, entry_ts, entry_price, qty, stop, tp, max_hold_until)` — mutable.
  - `JournalEvent(ts, kind: str, symbol: str, reason: str, payload: dict)` — frozen; `kind` ∈ {"decision","order","fill","exit","pnl","killswitch","error"}.
  - `config.SYMBOL`, `config.TIMEFRAME`, `config.LOOP_SECONDS`, `config.PROFILE` (a `StrategyProfile`), `config.CANDLE_DB`, `config.STATE_DB`, `config.JOURNAL_DB`.

- [x] **Step 1: Write the failing test `tests/test_contracts.py`**

```python
from datetime import datetime, timezone
from core_engine.contracts import Action, Decision, OrderIntent, EnginePosition, JournalEvent


def test_action_values():
    assert {a.value for a in Action} == {"enter_long", "hold", "exit"}


def test_decision_is_frozen():
    d = Decision(action=Action.HOLD, confidence=0.0, reason="flat regime", meta={})
    assert d.reason == "flat regime"
    try:
        d.confidence = 1.0
        raise AssertionError("Decision must be frozen")
    except AttributeError:
        pass


def test_order_intent_roundtrip():
    now = datetime(2026, 6, 17, tzinfo=timezone.utc)
    oi = OrderIntent(symbol="BTC/USD", qty=0.01, entry_price=100.0, stop=95.0,
                     tp=110.0, max_hold_until=now, reason="confluence pass")
    assert oi.qty == 0.01 and oi.symbol == "BTC/USD"


def test_journal_event_kinds():
    ev = JournalEvent(ts=datetime.now(timezone.utc), kind="decision",
                      symbol="BTC/USD", reason="hold", payload={"score": 0.3})
    assert ev.kind == "decision"
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_contracts.py -v`
Expected: FAIL with "No module named 'core_engine.contracts'".

- [x] **Step 3: Write `contracts.py`**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Action(str, Enum):
    ENTER_LONG = "enter_long"
    HOLD = "hold"
    EXIT = "exit"


@dataclass(frozen=True)
class Decision:
    action: Action
    confidence: float
    reason: str
    meta: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    qty: float
    entry_price: float
    stop: float
    tp: float
    max_hold_until: datetime
    reason: str


@dataclass
class EnginePosition:
    symbol: str
    entry_ts: datetime
    entry_price: float
    qty: float
    stop: float
    tp: float
    max_hold_until: datetime


@dataclass(frozen=True)
class JournalEvent:
    ts: datetime
    kind: str  # decision|order|fill|exit|pnl|killswitch|error
    symbol: str
    reason: str
    payload: dict = field(default_factory=dict)
```

- [x] **Step 4: Write `config.py`**

```python
from __future__ import annotations
import os
from swingbot.profile import StrategyProfile

SYMBOL = "BTC/USD"
TIMEFRAME = "5Min"
LOOP_SECONDS = 300

_DATA_DIR = os.environ.get("CORE_ENGINE_DATA", os.path.expanduser("~/.core-engine"))
os.makedirs(_DATA_DIR, exist_ok=True)
CANDLE_DB = os.path.join(_DATA_DIR, "candles.db")
STATE_DB = os.path.join(_DATA_DIR, "state.db")
JOURNAL_DB = os.path.join(_DATA_DIR, "journal.db")

# Single long-only profile for BTC/USD. Read src/swingbot/profile.py for the
# full field set; this constructs the minimal viable profile for one instrument.
PROFILE = StrategyProfile.btc_default() if hasattr(StrategyProfile, "btc_default") else StrategyProfile(symbol=SYMBOL)
```

> Implementer note: open `src/swingbot/profile.py:9` and construct `PROFILE` with the real required fields (risk fraction ~1%, ATR stop/tp mults, max-hold, confluence threshold, regime params). If a convenience constructor exists, use it; otherwise pass explicit values. Do not invent fields.

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_contracts.py -v`
Expected: 4 passed.

- [x] **Step 6: Commit**

```bash
git add lab/core-engine/src/core_engine/contracts.py lab/core-engine/src/core_engine/config.py lab/core-engine/tests/test_contracts.py
git commit -m "feat(core-engine): typed contracts + single-instrument config"
```

---

## Phase 1 — Pure modules (Codex-owned)

### Task 3: EngineJournal + report

**Files:**
- Create: `lab/core-engine/src/core_engine/journal.py`
- Test: `lab/core-engine/tests/test_journal.py`

**Interfaces:**
- Consumes: `JournalEvent` (Task 2).
- Produces:
  - `EngineJournal(db_path: str)`: `.log(event: JournalEvent) -> None`, `.events(kind: str | None = None, limit: int = 200) -> list[JournalEvent]`, `.closed_trades() -> list[dict]`.
  - `EngineJournal.report() -> Report` where `Report` is a frozen dataclass `(open_position: dict | None, realized_pnl: float, unrealized_pnl: float, wins: int, losses: int, closed: list[dict])`.

- [x] **Step 1: Write the failing test `tests/test_journal.py`**

```python
from datetime import datetime, timezone
from core_engine.contracts import JournalEvent
from core_engine.journal import EngineJournal


def _ev(kind, reason, **payload):
    return JournalEvent(ts=datetime.now(timezone.utc), kind=kind,
                        symbol="BTC/USD", reason=reason, payload=payload)


def test_log_and_read_back(tmp_path):
    j = EngineJournal(str(tmp_path / "j.db"))
    j.log(_ev("decision", "hold", score=0.2))
    j.log(_ev("order", "entry", qty=0.01))
    assert len(j.events()) == 2
    assert len(j.events(kind="order")) == 1


def test_report_counts_wins_losses(tmp_path):
    j = EngineJournal(str(tmp_path / "j.db"))
    j.log(_ev("pnl", "closed win", realized=12.0, won=True))
    j.log(_ev("pnl", "closed loss", realized=-5.0, won=False))
    r = j.report()
    assert r.wins == 1 and r.losses == 1
    assert round(r.realized_pnl, 2) == 7.0
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_journal.py -v`
Expected: FAIL with "No module named 'core_engine.journal'".

- [x] **Step 3: Write `journal.py`**

```python
from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from core_engine.contracts import JournalEvent


@dataclass(frozen=True)
class Report:
    open_position: dict | None
    realized_pnl: float
    unrealized_pnl: float
    wins: int
    losses: int
    closed: list[dict]


class EngineJournal:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, "
            "symbol TEXT, reason TEXT, payload TEXT)"
        )
        self._conn.commit()

    def log(self, event: JournalEvent) -> None:
        self._conn.execute(
            "INSERT INTO events (ts, kind, symbol, reason, payload) VALUES (?,?,?,?,?)",
            (event.ts.isoformat(), event.kind, event.symbol, event.reason,
             json.dumps(event.payload)),
        )
        self._conn.commit()

    def events(self, kind: str | None = None, limit: int = 200) -> list[JournalEvent]:
        sql = "SELECT ts, kind, symbol, reason, payload FROM events"
        args: tuple = ()
        if kind is not None:
            sql += " WHERE kind = ?"
            args = (kind,)
        sql += " ORDER BY id DESC LIMIT ?"
        args += (limit,)
        rows = self._conn.execute(sql, args).fetchall()
        return [
            JournalEvent(ts=datetime.fromisoformat(r[0]), kind=r[1], symbol=r[2],
                         reason=r[3], payload=json.loads(r[4]))
            for r in rows
        ]

    def closed_trades(self) -> list[dict]:
        return [e.payload for e in self.events(kind="pnl", limit=10_000)]

    def report(self) -> Report:
        pnls = self.closed_trades()
        wins = sum(1 for p in pnls if p.get("won") is True)
        losses = sum(1 for p in pnls if p.get("won") is False)
        realized = sum(float(p.get("realized", 0.0)) for p in pnls)
        opens = self.events(kind="order", limit=1)
        open_pos = opens[0].payload if opens and opens[0].payload.get("open") else None
        unrealized = float(open_pos.get("unrealized", 0.0)) if open_pos else 0.0
        return Report(open_position=open_pos, realized_pnl=realized,
                      unrealized_pnl=unrealized, wins=wins, losses=losses, closed=pnls)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_journal.py -v`
Expected: 2 passed.

- [x] **Step 5: Commit**

```bash
git add lab/core-engine/src/core_engine/journal.py lab/core-engine/tests/test_journal.py
git commit -m "feat(core-engine): durable journal + report"
```

---

### Task 4: Pure decision brain

**Files:**
- Create: `lab/core-engine/src/core_engine/brain.py`
- Create/extend: `lab/core-engine/tests/conftest.py` (FakeKronos + fixture window)
- Test: `lab/core-engine/tests/test_brain.py`

**Interfaces:**
- Consumes: `Action`, `Decision` (Task 2); `swingbot.regime.RegimeFilter`, `swingbot.confluence.{build_signals,ConfluenceEngine}`, `swingbot.types.MarketContext`, `StrategyProfile`.
- Produces: `decide(ctx: MarketContext, has_position: bool, *, profile: StrategyProfile, kronos) -> Decision`. **Pure**: no I/O, no globals, no clock. `kronos` is an object with `.evaluate(ctx) -> SignalResult` (the real `KronosForecastSignal` in prod, a fake in tests).

- [x] **Step 1: Add fakes to `tests/conftest.py`**

```python
import pandas as pd
import pytest
from swingbot.types import SignalResult


class FakeKronos:
    def __init__(self, score: float):
        self._score = score
    def evaluate(self, ctx):
        return SignalResult(name="kronos", score=self._score, meta={})


@pytest.fixture
def uptrend_window():
    # 60 ascending 5-min bars — read src/swingbot/types.py:123 for required columns.
    closes = [100 + i * 0.5 for i in range(60)]
    return pd.DataFrame({
        "open": closes, "high": [c + 0.3 for c in closes],
        "low": [c - 0.3 for c in closes], "close": closes,
        "volume": [10.0] * 60,
    })
```

- [x] **Step 2: Write the failing test `tests/test_brain.py`**

```python
from swingbot.types import MarketContext
from core_engine.contracts import Action
from core_engine.brain import decide
from core_engine.config import PROFILE


def test_holds_when_already_in_position(uptrend_window):
    ctx = MarketContext(candles=uptrend_window)
    d = decide(ctx, has_position=True, profile=PROFILE, kronos=None)
    assert d.action == Action.HOLD
    assert "in position" in d.reason.lower()


def test_decide_is_pure_no_side_effects(uptrend_window, monkeypatch):
    ctx = MarketContext(candles=uptrend_window)
    from tests.conftest import FakeKronos
    d1 = decide(ctx, has_position=False, profile=PROFILE, kronos=FakeKronos(0.9))
    d2 = decide(ctx, has_position=False, profile=PROFILE, kronos=FakeKronos(0.9))
    assert d1 == d2  # deterministic
    assert d1.action in (Action.ENTER_LONG, Action.HOLD)
```

- [x] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_brain.py -v`
Expected: FAIL with "No module named 'core_engine.brain'".

- [x] **Step 4: Write `brain.py`**

```python
from __future__ import annotations
from swingbot.confluence import ConfluenceEngine, build_signals
from swingbot.regime import RegimeFilter
from swingbot.types import MarketContext
from core_engine.contracts import Action, Decision


def decide(ctx: MarketContext, has_position: bool, *, profile, kronos) -> Decision:
    """Pure long-only entry decision. Exits are handled separately (client-side)."""
    if has_position:
        return Decision(Action.HOLD, 0.0, "already in position", {})

    regime = RegimeFilter(profile).evaluate(ctx)
    if not RegimeFilter(profile).permits_entry(regime.regime):
        return Decision(Action.HOLD, 0.0, f"regime gate blocks entry: {regime.regime}",
                        {"regime": regime.regime})

    conf = ConfluenceEngine(build_signals(profile), profile).evaluate(ctx)
    kron = kronos.evaluate(ctx).score if kronos is not None else 0.0
    if not conf.passed:
        return Decision(Action.HOLD, conf.score,
                        f"confluence {conf.score:.2f} < {conf.threshold:.2f}",
                        {"confluence": conf.score, "kronos": kron})

    confidence = min(1.0, 0.5 * conf.score + 0.5 * kron)
    return Decision(Action.ENTER_LONG, confidence,
                    f"confluence pass {conf.score:.2f}, kronos {kron:.2f}",
                    {"confluence": conf.score, "kronos": kron, "regime": regime.regime})
```

> Implementer note: confirm `RegimeFilter.permits_entry` / `ConfluenceResult.passed` semantics against `src/swingbot/regime.py` and `src/swingbot/confluence.py`. If `build_signals` already includes the Kronos signal for this profile, drop the separate `kronos` blend and read it from `conf.signals["kronos"]` instead — do not double-count.

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_brain.py -v`
Expected: 2 passed.

- [x] **Step 6: Commit**

```bash
git add lab/core-engine/src/core_engine/brain.py lab/core-engine/tests/test_brain.py lab/core-engine/tests/conftest.py
git commit -m "feat(core-engine): pure decision brain (regime+confluence+kronos)"
```

---

### Task 5: Risk gate (Decision → OrderIntent)

**Files:**
- Create: `lab/core-engine/src/core_engine/risk_gate.py`
- Test: `lab/core-engine/tests/test_risk_gate.py`

**Interfaces:**
- Consumes: `Decision`, `Action`, `OrderIntent` (Task 2); `swingbot.risk.{RiskManager,RiskState,RiskDecision}`, `swingbot.exits.bracket_levels`.
- Produces: `build_order_intent(decision, *, symbol, now, equity, entry_price, atr, risk: RiskManager, profile) -> OrderIntent | None`. Returns `None` (vetoed) when the decision is not `ENTER_LONG` or a risk gate blocks; the caller journals the veto reason from `risk.check_can_enter`.

- [x] **Step 1: Write the failing test `tests/test_risk_gate.py`**

```python
from datetime import datetime, timezone
from core_engine.contracts import Action, Decision
from core_engine.risk_gate import build_order_intent
from core_engine.config import PROFILE
from swingbot.risk import RiskManager, RiskState


def _risk():
    rm = RiskManager(PROFILE, RiskState())
    rm.start_day(datetime(2026, 6, 17, tzinfo=timezone.utc), equity=10_000.0)
    return rm


def test_non_entry_decision_yields_no_intent():
    d = Decision(Action.HOLD, 0.0, "hold", {})
    assert build_order_intent(d, symbol="BTC/USD",
                              now=datetime(2026, 6, 17, tzinfo=timezone.utc),
                              equity=10_000.0, entry_price=100.0, atr=2.0,
                              risk=_risk(), profile=PROFILE) is None


def test_entry_decision_sizes_and_brackets():
    d = Decision(Action.ENTER_LONG, 0.8, "confluence pass", {})
    oi = build_order_intent(d, symbol="BTC/USD",
                            now=datetime(2026, 6, 17, tzinfo=timezone.utc),
                            equity=10_000.0, entry_price=100.0, atr=2.0,
                            risk=_risk(), profile=PROFILE)
    assert oi is not None
    assert oi.qty > 0 and oi.stop < oi.entry_price < oi.tp
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_risk_gate.py -v`
Expected: FAIL with "No module named 'core_engine.risk_gate'".

- [x] **Step 3: Write `risk_gate.py`**

```python
from __future__ import annotations
from datetime import datetime, timedelta
from swingbot.exits import bracket_levels
from core_engine.contracts import Action, Decision, OrderIntent


def build_order_intent(decision: Decision, *, symbol: str, now: datetime,
                       equity: float, entry_price: float, atr: float,
                       risk, profile) -> OrderIntent | None:
    if decision.action is not Action.ENTER_LONG:
        return None

    gate = risk.check_can_enter(symbol, now)
    if not getattr(gate, "allowed", True):
        return None

    stop, tp = bracket_levels(entry_price, atr,
                              profile.stop_atr_mult, profile.tp_atr_mult)
    qty = risk.size(equity, entry_price, stop)
    if qty <= 0:
        return None

    max_hold = now + timedelta(minutes=profile.max_hold_minutes)
    return OrderIntent(symbol=symbol, qty=qty, entry_price=entry_price,
                       stop=stop, tp=tp, max_hold_until=max_hold,
                       reason=decision.reason)
```

> Implementer note: confirm `RiskDecision`'s allow flag name (`allowed`/`ok`/`can_enter`) in `src/swingbot/risk.py`, and the profile field names (`stop_atr_mult`, `tp_atr_mult`, `max_hold_minutes`) in `src/swingbot/profile.py`. Adjust the attribute names to match; do not invent them.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_risk_gate.py -v`
Expected: 2 passed.

- [x] **Step 5: Commit**

```bash
git add lab/core-engine/src/core_engine/risk_gate.py lab/core-engine/tests/test_risk_gate.py
git commit -m "feat(core-engine): risk gate builds sized, bracketed order intent"
```

---

### Task 6: Backtest harness (shared decide→risk→exit path)

**Files:**
- Create: `lab/core-engine/src/core_engine/backtest.py`
- Test: `lab/core-engine/tests/test_backtest.py`

**Interfaces:**
- Consumes: `decide` (Task 4), `build_order_intent` (Task 5), `swingbot.exits.exit_decision`, `EnginePosition`, `Action`.
- Produces: `run_backtest(candles: pd.DataFrame, *, profile, kronos, equity0: float = 10_000.0) -> BacktestResult` where `BacktestResult(trades: list[dict], final_equity: float, wins: int, losses: int)`. Walks bars front-to-back, opening/closing one position at a time using the **same** `decide`/exit logic the live loop uses.

- [x] **Step 1: Write the failing test `tests/test_backtest.py`**

```python
import pandas as pd
from core_engine.backtest import run_backtest
from core_engine.config import PROFILE
from tests.conftest import FakeKronos


def test_backtest_runs_and_returns_result():
    closes = [100 + (i % 20) * 0.5 for i in range(200)]
    candles = pd.DataFrame({
        "open": closes, "high": [c + 0.5 for c in closes],
        "low": [c - 0.5 for c in closes], "close": closes,
        "volume": [10.0] * 200,
    })
    res = run_backtest(candles, profile=PROFILE, kronos=FakeKronos(0.9))
    assert res.final_equity > 0
    assert res.wins + res.losses == len(res.trades)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_backtest.py -v`
Expected: FAIL with "No module named 'core_engine.backtest'".

- [x] **Step 3: Write `backtest.py`**

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import pandas as pd
from swingbot.exits import exit_decision
from swingbot.types import MarketContext
from swingbot.risk import RiskManager, RiskState
from core_engine.contracts import Action
from core_engine.brain import decide
from core_engine.risk_gate import build_order_intent


@dataclass(frozen=True)
class BacktestResult:
    trades: list[dict]
    final_equity: float
    wins: int
    losses: int


def _atr(window: pd.DataFrame, n: int = 14) -> float:
    hl = (window["high"] - window["low"]).tail(n)
    return float(hl.mean()) if len(hl) else 1.0


def run_backtest(candles: pd.DataFrame, *, profile, kronos,
                 equity0: float = 10_000.0) -> BacktestResult:
    equity = equity0
    pos = None
    trades: list[dict] = []
    risk = RiskManager(profile, RiskState())
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    risk.start_day(start, equity)

    for i in range(30, len(candles)):
        window = candles.iloc[: i + 1]
        bar = candles.iloc[i]
        now = start
        if pos is not None:
            ex = exit_decision(pos["stop"], pos["tp"], pos["max_hold_until"],
                               float(bar["high"]), float(bar["low"]),
                               float(bar["close"]), now)
            if ex is not None:
                reason, price = ex
                pnl = (price - pos["entry_price"]) * pos["qty"]
                equity += pnl
                trades.append({"pnl": pnl, "reason": str(reason), "won": pnl > 0})
                pos = None
            continue
        d = decide(MarketContext(candles=window), has_position=False,
                   profile=profile, kronos=kronos)
        if d.action is Action.ENTER_LONG:
            oi = build_order_intent(d, symbol="BTC/USD", now=now, equity=equity,
                                    entry_price=float(bar["close"]),
                                    atr=_atr(window), risk=risk, profile=profile)
            if oi is not None:
                pos = {"entry_price": oi.entry_price, "qty": oi.qty, "stop": oi.stop,
                       "tp": oi.tp, "max_hold_until": oi.max_hold_until}

    wins = sum(1 for t in trades if t["won"])
    return BacktestResult(trades=trades, final_equity=equity,
                          wins=wins, losses=len(trades) - wins)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backtest.py -v`
Expected: 1 passed.

- [x] **Step 5: Commit**

```bash
git add lab/core-engine/src/core_engine/backtest.py lab/core-engine/tests/test_backtest.py
git commit -m "feat(core-engine): backtest harness over shared decide/exit path"
```

---

## Phase 2 — Live-environment modules (Claude-owned)

### Task 7: MarketContext builder from the candle store

**Files:**
- Create: `lab/core-engine/src/core_engine/market.py`
- Test: `lab/core-engine/tests/test_market.py`

**Interfaces:**
- Consumes: `swingbot.data.store.CandleStore`, `swingbot.data.alpaca` (live fetch), `swingbot.types.MarketContext`, `config.{SYMBOL,TIMEFRAME,CANDLE_DB}`.
- Produces:
  - `refresh_candles(store: CandleStore, fetcher) -> int` — fetch latest 5-min bars and upsert; returns rows added. `fetcher` is injected (real `swingbot.data.alpaca` client in prod, fake in tests).
  - `build_context(store: CandleStore, lookback: int = 300) -> MarketContext` — read the last `lookback` bars into a DataFrame with the columns the v1 signals expect and wrap in `MarketContext`.
  - `latest_price(store) -> float`, `latest_atr(store, n: int = 14) -> float`.

- [x] **Step 1: Write the failing test `tests/test_market.py`**

```python
import pandas as pd
from swingbot.data.store import CandleStore
from core_engine.market import build_context, latest_price


def _seed(store):
    closes = [100 + i * 0.2 for i in range(50)]
    df = pd.DataFrame({
        "ts": pd.date_range("2026-06-17", periods=50, freq="5min", tz="UTC"),
        "open": closes, "high": [c + 0.2 for c in closes],
        "low": [c - 0.2 for c in closes], "close": closes, "volume": [5.0] * 50,
    })
    store.upsert_df("BTC/USD", "5Min", df)


def test_build_context_returns_dataframe(tmp_path):
    store = CandleStore(str(tmp_path / "c.db"))
    _seed(store)
    ctx = build_context(store, lookback=30)
    assert len(ctx.candles) == 30
    assert {"open", "high", "low", "close"} <= set(ctx.candles.columns)


def test_latest_price(tmp_path):
    store = CandleStore(str(tmp_path / "c.db"))
    _seed(store)
    assert latest_price(store) > 100
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_market.py -v`
Expected: FAIL with "No module named 'core_engine.market'".

- [x] **Step 3: Write `market.py`**

```python
from __future__ import annotations
import pandas as pd
from swingbot.types import MarketContext
from core_engine.config import SYMBOL, TIMEFRAME


def _frame(store, lookback: int) -> pd.DataFrame:
    rows = store.get(SYMBOL, TIMEFRAME, limit=lookback)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("ts").reset_index(drop=True)


def refresh_candles(store, fetcher) -> int:
    """Fetch latest 5-min bars via injected fetcher and upsert. Returns rows added."""
    df = fetcher.fetch(SYMBOL, TIMEFRAME)
    if df is None or len(df) == 0:
        return 0
    return store.upsert_df(SYMBOL, TIMEFRAME, df)


def build_context(store, lookback: int = 300) -> MarketContext:
    return MarketContext(candles=_frame(store, lookback))


def latest_price(store) -> float:
    df = _frame(store, 1)
    return float(df["close"].iloc[-1])


def latest_atr(store, n: int = 14) -> float:
    df = _frame(store, n + 1)
    hl = (df["high"] - df["low"]).tail(n)
    return float(hl.mean()) if len(hl) else 1.0
```

> Implementer note: confirm `CandleStore.get` row keys (`ts`/`open`/...) against `src/swingbot/data/store.py:63`. If `ts` comes back as a string, parse to datetime here. Confirm the `swingbot.data.alpaca` fetch entrypoint signature and adapt `refresh_candles`'s `fetcher.fetch(...)` call to it.

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_market.py -v`
Expected: 2 passed.

- [x] **Step 5: Commit**

```bash
git add lab/core-engine/src/core_engine/market.py lab/core-engine/tests/test_market.py
git commit -m "feat(core-engine): MarketContext builder over candle store"
```

---

### Task 8: Executor (place / track / reconcile / exit)

**Files:**
- Create: `lab/core-engine/src/core_engine/executor.py`
- Extend: `lab/core-engine/tests/conftest.py` (add `FakeBroker` with a `pending_new` stall)
- Test: `lab/core-engine/tests/test_executor.py`

**Interfaces:**
- Consumes: `swingbot.broker.base.Broker`, `swingbot.types.OrderStatus`, `OrderIntent`, `EnginePosition`.
- Produces:
  - `Executor(broker)`:
    - `.enter(intent: OrderIntent, now) -> EnginePosition | None` — submit market buy; if the fill confirms, return an `EnginePosition`; if the order is still `pending_new`/unfilled, return `None` (truthful — caller journals "entry pending", does NOT record a position).
    - `.exit(position: EnginePosition, price: float, reason: str) -> float | None` — submit market sell; return realized pnl on confirmed fill, else `None`.
    - `.reconcile(position: EnginePosition | None) -> EnginePosition | None` — pull broker truth (`get_position`) and correct/clear local position.

- [x] **Step 1: Add `FakeBroker` to `tests/conftest.py`**

```python
class FakeBroker:
    """Models the Alpaca paper crypto BUY pending_new stall + instant SELL fill."""
    def __init__(self, buy_stalls: bool = False):
        self.buy_stalls = buy_stalls
        self._position = None
        self.orders = {}

    def submit_market_buy(self, symbol, qty, **kw):
        oid = f"buy-{len(self.orders)}"
        status = "pending_new" if self.buy_stalls else "filled"
        self.orders[oid] = {"id": oid, "status": status, "filled_avg_price": 100.0,
                            "filled_qty": 0.0 if self.buy_stalls else qty}
        if not self.buy_stalls:
            self._position = {"symbol": symbol, "qty": qty, "avg_entry_price": 100.0}
        return self.orders[oid]

    def submit_market_sell(self, symbol, qty, **kw):
        oid = f"sell-{len(self.orders)}"
        self.orders[oid] = {"id": oid, "status": "filled", "filled_avg_price": 105.0,
                            "filled_qty": qty}
        self._position = None
        return self.orders[oid]

    def get_order(self, order_id, **kw):
        return self.orders.get(order_id)

    def get_position(self, symbol):
        return self._position

    def equity(self, mark_price):
        return 10_000.0
```

- [x] **Step 2: Write the failing test `tests/test_executor.py`**

```python
from datetime import datetime, timezone
from core_engine.contracts import OrderIntent
from core_engine.executor import Executor
from tests.conftest import FakeBroker


def _intent():
    return OrderIntent(symbol="BTC/USD", qty=0.01, entry_price=100.0, stop=95.0,
                       tp=110.0, max_hold_until=datetime(2026, 6, 17, tzinfo=timezone.utc),
                       reason="test")


def test_filled_buy_returns_position():
    pos = Executor(FakeBroker(buy_stalls=False)).enter(
        _intent(), now=datetime(2026, 6, 17, tzinfo=timezone.utc))
    assert pos is not None and pos.qty == 0.01


def test_pending_buy_returns_none_truthfully():
    pos = Executor(FakeBroker(buy_stalls=True)).enter(
        _intent(), now=datetime(2026, 6, 17, tzinfo=timezone.utc))
    assert pos is None  # never report a position on an unfilled order


def test_exit_returns_realized_pnl():
    broker = FakeBroker(buy_stalls=False)
    ex = Executor(broker)
    pos = ex.enter(_intent(), now=datetime(2026, 6, 17, tzinfo=timezone.utc))
    pnl = ex.exit(pos, price=105.0, reason="take_profit")
    assert round(pnl, 2) == round((105.0 - 100.0) * 0.01, 2)
```

- [x] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_executor.py -v`
Expected: FAIL with "No module named 'core_engine.executor'".

- [x] **Step 4: Write `executor.py`**

```python
from __future__ import annotations
from core_engine.contracts import EnginePosition, OrderIntent


def _is_filled(order: dict | None) -> bool:
    return bool(order) and str(order.get("status", "")).lower() == "filled"


class Executor:
    def __init__(self, broker):
        self._broker = broker

    def enter(self, intent: OrderIntent, now) -> EnginePosition | None:
        order = self._broker.submit_market_buy(intent.symbol, intent.qty)
        if not _is_filled(order):
            return None  # truthful: pending_new / unfilled -> no position
        fill = float(order.get("filled_avg_price", intent.entry_price))
        return EnginePosition(symbol=intent.symbol, entry_ts=now, entry_price=fill,
                              qty=intent.qty, stop=intent.stop, tp=intent.tp,
                              max_hold_until=intent.max_hold_until)

    def exit(self, position: EnginePosition, price: float, reason: str) -> float | None:
        order = self._broker.submit_market_sell(position.symbol, position.qty)
        if not _is_filled(order):
            return None
        fill = float(order.get("filled_avg_price", price))
        return (fill - position.entry_price) * position.qty

    def reconcile(self, position: EnginePosition | None) -> EnginePosition | None:
        truth = self._broker.get_position(position.symbol if position else "BTC/USD")
        if truth is None:
            return None  # broker says flat -> we are flat
        if position is None:
            # Broker holds a position we don't track — adopt minimal truth.
            return EnginePosition(symbol=truth["symbol"], entry_ts=None,
                                  entry_price=float(truth["avg_entry_price"]),
                                  qty=float(truth["qty"]), stop=0.0, tp=0.0,
                                  max_hold_until=None)
        return position
```

> Implementer note: confirm the live `swingbot.broker.alpaca` order dict keys (`status`, `filled_avg_price`, `filled_qty`) and `get_position` keys against `src/swingbot/broker/alpaca.py`. The `pending_new` truthfulness contract is the whole point of this task — keep `_is_filled` strict.

- [x] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_executor.py -v`
Expected: 3 passed.

- [x] **Step 6: Commit**

```bash
git add lab/core-engine/src/core_engine/executor.py lab/core-engine/tests/test_executor.py lab/core-engine/tests/conftest.py
git commit -m "feat(core-engine): executor with truthful pending_new handling"
```

---

### Task 9: The tick loop orchestrator + auto-resume

**Files:**
- Create: `lab/core-engine/src/core_engine/loop.py`
- Test: `lab/core-engine/tests/test_loop.py`

**Interfaces:**
- Consumes: `build_context`,`refresh_candles`,`latest_price`,`latest_atr` (Task 7); `decide` (Task 4); `build_order_intent` (Task 5); `Executor` (Task 8); `EngineJournal` (Task 3); `swingbot.exits.exit_decision`; `swingbot.runtime_state.RuntimeStateStore`; `swingbot.risk.{RiskManager,RiskState}`.
- Produces:
  - `Engine(*, store, fetcher, broker, journal, risk, runtime_state, profile, kronos)` with `.tick(now) -> None` (one full pipeline pass; **never raises** — all stage errors are caught + journaled) and `.run_forever()` (sleep-loop on `config.LOOP_SECONDS`, gated by `runtime_state.get_running_desired()`).
  - State held in `Engine.position: EnginePosition | None`.

- [ ] **Step 1: Write the failing test `tests/test_loop.py`**

```python
from datetime import datetime, timezone
import pandas as pd
from swingbot.data.store import CandleStore
from swingbot.risk import RiskManager, RiskState
from core_engine.journal import EngineJournal
from core_engine.loop import Engine
from core_engine.config import PROFILE
from tests.conftest import FakeBroker, FakeKronos


class _Fetcher:
    def fetch(self, symbol, timeframe):
        return None  # candles pre-seeded; no live fetch in test


class _RT:
    def get_running_desired(self): return True
    def set_running_desired(self, v): pass


def _seed(store):
    closes = [100 + i * 0.5 for i in range(80)]
    df = pd.DataFrame({
        "ts": pd.date_range("2026-06-17", periods=80, freq="5min", tz="UTC"),
        "open": closes, "high": [c + 0.4 for c in closes],
        "low": [c - 0.4 for c in closes], "close": closes, "volume": [9.0] * 80,
    })
    store.upsert_df("BTC/USD", "5Min", df)


def test_one_tick_never_raises_and_journals(tmp_path):
    store = CandleStore(str(tmp_path / "c.db")); _seed(store)
    journal = EngineJournal(str(tmp_path / "j.db"))
    risk = RiskManager(PROFILE, RiskState())
    eng = Engine(store=store, fetcher=_Fetcher(), broker=FakeBroker(),
                 journal=journal, risk=risk, runtime_state=_RT(),
                 profile=PROFILE, kronos=FakeKronos(0.95))
    eng.tick(datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc))
    assert len(journal.events()) >= 1  # at minimum a decision was journaled


def test_tick_swallows_stage_errors(tmp_path):
    store = CandleStore(str(tmp_path / "c.db"))  # empty -> build_context will fail
    journal = EngineJournal(str(tmp_path / "j.db"))
    eng = Engine(store=store, fetcher=_Fetcher(), broker=FakeBroker(),
                 journal=journal, risk=RiskManager(PROFILE, RiskState()),
                 runtime_state=_RT(), profile=PROFILE, kronos=FakeKronos(0.1))
    eng.tick(datetime(2026, 6, 17, 12, 0, tzinfo=timezone.utc))  # must not raise
    assert any(e.kind == "error" for e in journal.events())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_loop.py -v`
Expected: FAIL with "No module named 'core_engine.loop'".

- [ ] **Step 3: Write `loop.py`**

```python
from __future__ import annotations
import time
from datetime import datetime, timezone
from swingbot.exits import exit_decision
from core_engine.config import LOOP_SECONDS, SYMBOL
from core_engine.contracts import Action, JournalEvent
from core_engine.brain import decide
from core_engine.risk_gate import build_order_intent
from core_engine.executor import Executor
from core_engine.market import build_context, refresh_candles, latest_price, latest_atr


class Engine:
    def __init__(self, *, store, fetcher, broker, journal, risk, runtime_state,
                 profile, kronos):
        self._store = store
        self._fetcher = fetcher
        self._broker = broker
        self._journal = journal
        self._risk = risk
        self._rt = runtime_state
        self._profile = profile
        self._kronos = kronos
        self._exec = Executor(broker)
        self.position = None

    def _log(self, kind, reason, **payload):
        self._journal.log(JournalEvent(ts=datetime.now(timezone.utc), kind=kind,
                                       symbol=SYMBOL, reason=reason, payload=payload))

    def tick(self, now: datetime) -> None:
        try:
            refresh_candles(self._store, self._fetcher)
            self.position = self._exec.reconcile(self.position)

            if self.position is not None:
                price = latest_price(self._store)
                ex = exit_decision(self.position.stop, self.position.tp,
                                   self.position.max_hold_until, price, price, price, now)
                if ex is not None:
                    reason, ref = ex
                    pnl = self._exec.exit(self.position, ref, str(reason))
                    if pnl is None:
                        self._log("exit", "exit order unfilled", reason=str(reason))
                    else:
                        self._log("pnl", f"closed: {reason}", realized=pnl, won=pnl > 0)
                        self.position = None
                return

            ctx = build_context(self._store)
            d = decide(ctx, has_position=False, profile=self._profile, kronos=self._kronos)
            self._log("decision", d.reason, action=d.action.value,
                      confidence=d.confidence)
            if d.action is not Action.ENTER_LONG:
                return

            price = latest_price(self._store)
            equity = self._broker.equity(price)
            self._risk.start_day(now, equity)
            intent = build_order_intent(d, symbol=SYMBOL, now=now, equity=equity,
                                        entry_price=price, atr=latest_atr(self._store),
                                        risk=self._risk, profile=self._profile)
            if intent is None:
                self._log("decision", "risk gate vetoed entry")
                return
            pos = self._exec.enter(intent, now)
            if pos is None:
                self._log("order", "entry pending / unfilled", qty=intent.qty)
            else:
                self.position = pos
                self._log("order", "entry filled", open=True, qty=pos.qty,
                          entry=pos.entry_price)
        except Exception as exc:  # the loop never dies
            self._log("error", f"tick failed: {type(exc).__name__}: {exc}")

    def run_forever(self) -> None:
        while True:
            if self._rt.get_running_desired():
                self.tick(datetime.now(timezone.utc))
            time.sleep(LOOP_SECONDS)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_loop.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run the full suite**

Run: `cd lab/core-engine && pytest -v`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add lab/core-engine/src/core_engine/loop.py lab/core-engine/tests/test_loop.py
git commit -m "feat(core-engine): failure-tolerant tick loop + auto-resume"
```

---

### Task 10: CLI entrypoint + Dockerfile + live acceptance

**Files:**
- Create: `lab/core-engine/src/core_engine/__main__.py`
- Create: `lab/core-engine/Dockerfile`
- Create: `lab/core-engine/docs/LIVE_ACCEPTANCE.md`

**Interfaces:**
- Consumes: everything above; wires real `swingbot.broker.alpaca`, `swingbot.signals.kronos_forecast.KronosForecastSignal`, `swingbot.data.alpaca` fetcher, `RuntimeStateStore(config.STATE_DB)`, `EngineJournal(config.JOURNAL_DB)`, `CandleStore(config.CANDLE_DB)`.
- Produces: `python -m core_engine {run|report|backtest}`.

- [ ] **Step 1: Write `__main__.py`**

```python
from __future__ import annotations
import argparse
from swingbot.data.store import CandleStore
from swingbot.runtime_state import RuntimeStateStore
from swingbot.risk import RiskManager, RiskState
from core_engine.config import CANDLE_DB, STATE_DB, JOURNAL_DB, PROFILE
from core_engine.journal import EngineJournal


def _build_engine():
    from swingbot.broker.alpaca import AlpacaBroker  # confirm class name in alpaca.py
    from swingbot.signals.kronos_forecast import KronosForecastSignal
    from swingbot.data import alpaca as alpaca_data
    from core_engine.loop import Engine
    store = CandleStore(CANDLE_DB)
    journal = EngineJournal(JOURNAL_DB)
    return Engine(store=store, fetcher=alpaca_data, broker=AlpacaBroker.from_env(),
                  journal=journal, risk=RiskManager(PROFILE, RiskState()),
                  runtime_state=RuntimeStateStore(STATE_DB), profile=PROFILE,
                  kronos=KronosForecastSignal())


def _cmd_report():
    r = EngineJournal(JOURNAL_DB).report()
    print(f"Open position: {r.open_position}")
    print(f"Realized P&L:  {r.realized_pnl:.2f}   Unrealized: {r.unrealized_pnl:.2f}")
    print(f"Wins/Losses:   {r.wins}/{r.losses}")
    for t in r.closed[:20]:
        print(f"  {t.get('reason')}: {t.get('realized', 0):.2f}")


def main():
    p = argparse.ArgumentParser(prog="core_engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("report")
    bt = sub.add_parser("backtest")
    bt.add_argument("--limit", type=int, default=2000)
    args = p.parse_args()

    if args.cmd == "run":
        eng = _build_engine()
        RuntimeStateStore(STATE_DB).set_running_desired(True)
        eng.run_forever()
    elif args.cmd == "report":
        _cmd_report()
    elif args.cmd == "backtest":
        import pandas as pd
        from core_engine.backtest import run_backtest
        from swingbot.signals.kronos_forecast import KronosForecastSignal
        rows = CandleStore(CANDLE_DB).get("BTC/USD", "5Min", limit=args.limit)
        res = run_backtest(pd.DataFrame(rows), profile=PROFILE,
                           kronos=KronosForecastSignal())
        print(f"Backtest: trades={len(res.trades)} wins={res.wins} "
              f"losses={res.losses} final_equity={res.final_equity:.2f}")


if __name__ == "__main__":
    main()
```

> Implementer note: confirm the real Alpaca broker class + constructor (`AlpacaBroker.from_env()` is a guess) in `src/swingbot/broker/alpaca.py`, the `KronosForecastSignal.__init__` required args in `src/swingbot/signals/kronos_forecast.py`, and the `swingbot.data.alpaca` fetch entrypoint. Wire the real names.

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
# Build context is the repo root so we can install the parent swingbot package.
COPY . /app
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir -e lab/core-engine
ENV CORE_ENGINE_DATA=/data
VOLUME /data
CMD ["python", "-m", "core_engine", "run"]
```

- [ ] **Step 3: Write `docs/LIVE_ACCEPTANCE.md`** (the manual runbook)

```markdown
# Live acceptance — core-engine

1. Backfill ~5 days of 5-min BTC/USD candles into $CORE_ENGINE_DATA/candles.db.
2. `python -m core_engine backtest --limit 1500` → prints a sane trade count + final equity.
3. `python -m core_engine run` (paper) → leave one full 5-min tick to elapse.
4. `python -m core_engine report` → shows a decision was made; if it entered, an open
   position with stop/tp; P&L line present.
5. Kill the process, restart `run` → it auto-resumes (running_desired persisted).
6. Confirm: a stalled (pending_new) BUY is reported as "entry pending", NOT as an open position.
```

- [ ] **Step 4: Build the isolated image and smoke-run report**

Run (from repo root):
```bash
docker build -f lab/core-engine/Dockerfile -t core-engine:dev .
docker run --rm -v core_engine_data:/data core-engine:dev python -m core_engine report
```
Expected: report prints (zeros on a fresh volume), no traceback.

- [ ] **Step 5: Live acceptance (Claude-only, real paper)**

Follow `docs/LIVE_ACCEPTANCE.md` against Alpaca paper. Record the outcome of each step.
Do NOT claim success until `report` shows a real decision/journal entry from a live tick.

- [ ] **Step 6: Commit**

```bash
git add lab/core-engine/src/core_engine/__main__.py lab/core-engine/Dockerfile lab/core-engine/docs/LIVE_ACCEPTANCE.md
git commit -m "feat(core-engine): CLI (run/report/backtest) + Docker + live acceptance runbook"
```

---

## Collaboration — Claude (clawd) + Codex (VM)

The module ownership above is the work split. Coordinate over the tmux bridge (ref: `codex-vm-bridge` memory).

- **Contracts first:** Task 1 + Task 2 land on `core-engine` before anything parallel. Codex branches `codex/core-engine` **off `core-engine`** only after Task 2 is committed and pushed.
- **Codex builds** Tasks 3, 4, 5, 6 (pure, fixture-tested — no live env needed). It pushes `codex/core-engine`; pings Claude `FROM CODEX: phase-1 ready` when done.
- **Claude builds** Tasks 7, 8, 9, 10 (need live Alpaca/Docker), then **integrates** Codex's branch into `core-engine`, runs the full suite, and does the live acceptance (Task 10 step 5). Claude is the integrator because only Claude can live-verify.
- **Handoff mechanics:** Claude → Codex: write task file → `scp` to VM → `tmux -L codex-managed load-buffer` → `paste-buffer -t codex` → `send-keys Enter`. Codex → Claude: `ssh redji@192.168.1.205` then `tmux load-buffer`/`paste-buffer -t claude`, prefix `FROM CODEX:`.
- **Docker rebuild** of the experiment image is Claude's, after every integrated change.
- **`master` stays untouched** for the entire experiment. Promotion of `core-engine` → `master` is a separate, later decision once live acceptance passes.

---

## Self-Review (completed)

- **Spec coverage:** §2 scope → Tasks 1–10; §3 pipeline → Task 9 `tick()`; pure `decide()` → Task 4; client-side exits → Tasks 6/9 via `exit_decision`; risk gates/kill-switch → Task 5 + Task 9 `start_day`; journal+report → Task 3 + Task 10; auto-resume → Task 9/10 `RuntimeStateStore`; backtest shared path → Task 6; truthful `pending_new` → Task 8; isolation → Task 1 + Global Constraints; Codex collab → §Collaboration. No uncovered requirement.
- **Placeholder scan:** no TBD/TODO. The "implementer note" blocks point at exact v1 files to confirm real attribute names (legitimate reuse verification), not deferred work.
- **Type consistency:** `Decision`, `Action`, `OrderIntent`, `EnginePosition`, `JournalEvent` defined in Task 2 and used with identical signatures in Tasks 3–10. `EngineJournal.log`, `Executor.enter/exit/reconcile`, `decide(...)`, `build_order_intent(...)`, `Engine.tick(...)` names match across producer/consumer blocks.
