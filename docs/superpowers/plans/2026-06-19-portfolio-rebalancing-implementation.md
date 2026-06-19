# Portfolio Rebalancing Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a portfolio rebalancing layer that gives each strategy a target weight, detects allocation drift, and corrects it via soft (sizing-only) or hard (active trim) mode with smart-timing guards — wired into the supervisor, sizing, telemetry, API, and dashboard.

**Architecture:** A new pure-logic module `swingbot/rebalance.py` (dataclasses + no-IO `Rebalancer`, mirroring `risk.py`/`portfolio_risk.py`) computes allocations, drift, and trims. Persistence reuses the existing SQLite stores (`ProfileStore` meta, a new `StateStore` table, a new telemetry table). The `PortfolioSupervisor` wires it into `tick_all`: soft mode injects per-strategy `allocated_equity` into sizing and caps growth in `_make_gate`; hard mode places reduce-only sells after the strategy loop. All guarded by kill switches, circuit breakers, and the paper/live gate. New API routes + a dashboard panel expose it.

**Tech Stack:** Python 3.11+, FastAPI, SQLite (stdlib `sqlite3`), pandas, pytest, React + Vite (lightweight-charts already present).

## Global Constraints

- Ships **off**: `RebalanceSettings.enabled = False`, `mode = "soft"`. With `enabled=False`, existing supervisor/orchestrator behavior must be **byte-for-byte preserved** (regression-tested).
- Allocation basis: `allocated_equity(S) = target_weight(S) × total_equity`. Weights ∈ [0,1], `sum ≤ 1.0`.
- Hard-mode trims are **minimal** (sell only down to just under `target + drift_threshold`) and **reduce-only sells** — rebalancing NEVER opens or enlarges a position.
- Mandatory safety: skip ALL trims when the portfolio kill switch / circuit breaker is active; never trim a strategy whose own `RiskState.kill_switch_active`; honor `self.mode` (paper/live) on every order; log every evaluation (ran or skipped) to telemetry.
- All pure-logic modules do **no IO**. TDD: write the failing test first, every task. Commit per task.
- Docker rebuild policy (standing rule): after code changes, `docker compose build swingbot && docker compose up -d swingbot`.
- Branch: `core-engine` (current checkout).

---

### Task 1: Rebalance dataclasses + allocation math

**Files:**
- Create: `src/swingbot/rebalance.py`
- Test: `tests/test_rebalance.py`

**Interfaces:**
- Produces: `RebalanceSettings`, `StrategyAllocation`, `RebalanceState`, `TrimAction`, `RebalanceResult` dataclasses; `allocated_equity(name, targets, total_equity, n_strategies) -> float`; `compute_allocations(deployed, symbols, targets, total_equity) -> list[StrategyAllocation]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rebalance.py
from swingbot.rebalance import (
    RebalanceSettings, StrategyAllocation, allocated_equity, compute_allocations,
)

def test_allocated_equity_uses_target_times_total():
    assert allocated_equity("a", {"a": 0.3}, 10_000, n_strategies=2) == 3_000.0

def test_allocated_equity_equal_weight_fallback_when_no_target():
    # no explicit target -> equal weight 1/N
    assert allocated_equity("a", {}, 10_000, n_strategies=4) == 2_500.0

def test_compute_allocations_actual_and_drift():
    allocs = compute_allocations(
        deployed={"a": 4_000.0, "b": 1_000.0},
        symbols={"a": "BTC/USD", "b": "ETH/USD"},
        targets={"a": 0.3, "b": 0.3},
        total_equity=10_000.0,
    )
    by = {x.name: x for x in allocs}
    assert by["a"].actual_weight == 0.4
    assert round(by["a"].drift, 4) == 0.1      # 0.4 - 0.3
    assert round(by["b"].drift, 4) == -0.2     # 0.1 - 0.3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd crypto-swing-bot && .venv/bin/pytest tests/test_rebalance.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.rebalance'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/swingbot/rebalance.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RebalanceSettings:
    enabled: bool = False
    mode: str = "soft"                 # "soft" | "hard"
    drift_threshold: float = 0.05
    min_interval_minutes: int = 1440
    vol_skip_threshold: float = 0.05
    vol_lookback: int = 24
    fee_rate: float = 0.0025
    benefit_factor: float = 1.0
    correlation_threshold: float = 0.8
    cash_buffer_frac: float = 0.0


@dataclass(frozen=True)
class StrategyAllocation:
    name: str
    symbol: str
    target_weight: float
    deployed_value: float
    actual_weight: float
    drift: float


@dataclass
class RebalanceState:
    last_rebalance_at: str = ""        # ISO8601 UTC, "" = never


@dataclass(frozen=True)
class TrimAction:
    name: str
    symbol: str
    qty: float
    value: float
    reason: str


@dataclass(frozen=True)
class RebalanceResult:
    ran: bool
    skipped_reason: str
    allocations: list[StrategyAllocation]
    trims: list[TrimAction]
    mode: str


def allocated_equity(name: str, targets: dict, total_equity: float,
                     n_strategies: int) -> float:
    weight = targets.get(name)
    if weight is None:
        weight = (1.0 / n_strategies) if n_strategies else 0.0
    return weight * total_equity


def compute_allocations(deployed: dict, symbols: dict, targets: dict,
                        total_equity: float) -> list[StrategyAllocation]:
    n = len(deployed)
    out = []
    for name in sorted(deployed):
        dv = deployed[name]
        target = targets.get(name, (1.0 / n) if n else 0.0)
        actual = (dv / total_equity) if total_equity else 0.0
        out.append(StrategyAllocation(
            name=name, symbol=symbols.get(name, ""), target_weight=target,
            deployed_value=dv, actual_weight=actual, drift=actual - target))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_rebalance.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/rebalance.py tests/test_rebalance.py
git commit -m "feat(rebalance): dataclasses + allocation/drift math"
```

---

### Task 2: Drift detection + volatility & correlation helpers

**Files:**
- Modify: `src/swingbot/rebalance.py`
- Test: `tests/test_rebalance.py`

**Interfaces:**
- Consumes: `StrategyAllocation`, `RebalanceSettings` (Task 1).
- Produces: `detect_drift(allocations, threshold) -> list[StrategyAllocation]` (overweight only); `recent_volatility(returns) -> float`; `correlation_clusters(returns_by_symbol, threshold) -> list[set[str]]`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_rebalance.py
import pandas as pd
from swingbot.rebalance import detect_drift, recent_volatility, correlation_clusters

def test_detect_drift_returns_only_overweight_beyond_threshold():
    allocs = compute_allocations(
        deployed={"a": 4_000.0, "b": 2_000.0}, symbols={"a": "X", "b": "Y"},
        targets={"a": 0.3, "b": 0.3}, total_equity=10_000.0)
    drifted = detect_drift(allocs, threshold=0.05)
    assert [d.name for d in drifted] == ["a"]   # a drift +0.10 > 0.05; b is underweight

def test_recent_volatility_is_stdev_of_returns():
    s = pd.Series([100, 110, 105, 115, 120], dtype=float)
    rets = s.pct_change().dropna()
    assert abs(recent_volatility(s) - rets.std()) < 1e-9

def test_correlation_clusters_groups_correlated_symbols():
    base = pd.Series([1, 2, 3, 4, 5], dtype=float)
    returns = {
        "A": base.pct_change().dropna(),
        "B": (base * 2).pct_change().dropna(),     # perfectly correlated with A
        "C": pd.Series([5, 1, 6, 2, 7]).pct_change().dropna(),
    }
    clusters = correlation_clusters(returns, threshold=0.8)
    assert any({"A", "B"} <= c for c in clusters)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_rebalance.py -k "drift or volatility or clusters" -v`
Expected: FAIL with `ImportError: cannot import name 'detect_drift'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/swingbot/rebalance.py
import pandas as pd


def detect_drift(allocations: list, threshold: float) -> list:
    return [a for a in allocations if a.drift > threshold]


def recent_volatility(prices: "pd.Series") -> float:
    rets = prices.pct_change().dropna()
    if len(rets) < 2:
        return 0.0
    return float(rets.std())


def correlation_clusters(returns_by_symbol: dict, threshold: float) -> list:
    syms = sorted(returns_by_symbol)
    clusters: list[set] = []
    for s in syms:
        placed = False
        for c in clusters:
            rep = next(iter(c))
            corr = returns_by_symbol[s].corr(returns_by_symbol[rep])
            if pd.notna(corr) and corr >= threshold:
                c.add(s)
                placed = True
                break
        if not placed:
            clusters.append({s})
    return clusters
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_rebalance.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/rebalance.py tests/test_rebalance.py
git commit -m "feat(rebalance): drift detection + volatility/correlation helpers"
```

---

### Task 3: `plan_trims` with vol / correlation / fee guards

**Files:**
- Modify: `src/swingbot/rebalance.py`
- Test: `tests/test_rebalance.py`

**Interfaces:**
- Consumes: `StrategyAllocation`, `RebalanceSettings`, `TrimAction`, `recent_volatility`, `correlation_clusters`.
- Produces: `plan_trims(drifted, all_allocations, prices, total_equity, settings, returns_by_symbol) -> tuple[list[TrimAction], list[str]]` (trims, skip_reasons).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_rebalance.py
from swingbot.rebalance import plan_trims

def _alloc(name, sym, target, deployed, total):
    return compute_allocations({name: deployed}, {name: sym}, {name: target}, total)[0]

def test_plan_trims_minimal_trim_to_just_under_band():
    a = _alloc("a", "BTC/USD", 0.3, 5_000.0, 10_000.0)   # actual 0.5, drift 0.2
    s = RebalanceSettings(drift_threshold=0.05, vol_skip_threshold=1.0,
                          fee_rate=0.0, benefit_factor=0.0)
    rets = {"BTC/USD": pd.Series([1, 2, 3, 4, 5]).pct_change().dropna()}
    trims, skips = plan_trims([a], [a], {"BTC/USD": 100.0}, 10_000.0, s, rets)
    # band ceiling = (0.3 + 0.05) * 10_000 = 3_500; trim value = 5_000 - 3_500 = 1_500
    assert len(trims) == 1
    assert round(trims[0].value, 2) == 1_500.0
    assert round(trims[0].qty, 4) == 15.0       # 1_500 / 100

def test_plan_trims_skips_on_high_volatility():
    a = _alloc("a", "BTC/USD", 0.3, 5_000.0, 10_000.0)
    s = RebalanceSettings(drift_threshold=0.05, vol_skip_threshold=0.0001,
                          fee_rate=0.0, benefit_factor=0.0)
    rets = {"BTC/USD": pd.Series([1, 5, 2, 9, 3]).pct_change().dropna()}  # high vol
    trims, skips = plan_trims([a], [a], {"BTC/USD": 100.0}, 10_000.0, s, rets)
    assert trims == []
    assert any("volatil" in r for r in skips)

def test_plan_trims_skips_when_below_min_notional():
    a = _alloc("a", "BTC/USD", 0.3, 3_600.0, 10_000.0)  # trim value = 100
    # min_trim_notional = benefit_factor * 2 * fee_rate * total = 1*2*0.0025*10_000 = 50
    # 100 > 50 would pass; set benefit_factor high to force a skip:
    s = RebalanceSettings(drift_threshold=0.05, vol_skip_threshold=1.0,
                          fee_rate=0.0025, benefit_factor=10.0)
    rets = {"BTC/USD": pd.Series([1, 2, 3, 4, 5]).pct_change().dropna()}
    trims, skips = plan_trims([a], [a], {"BTC/USD": 100.0}, 10_000.0, s, rets)
    assert trims == []
    assert any("fee" in r for r in skips)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_rebalance.py -k plan_trims -v`
Expected: FAIL with `ImportError: cannot import name 'plan_trims'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/swingbot/rebalance.py
def plan_trims(drifted: list, all_allocations: list, prices: dict,
               total_equity: float, settings: "RebalanceSettings",
               returns_by_symbol: dict) -> tuple[list, list]:
    trims: list = []
    skips: list = []
    min_trim_notional = settings.benefit_factor * 2 * settings.fee_rate * total_equity

    # correlation: pull underweight offset into the same cluster (avoid double-trim)
    clusters = correlation_clusters(returns_by_symbol, settings.correlation_threshold)
    under_by_symbol = {a.symbol: a for a in all_allocations if a.drift < 0}

    for a in drifted:
        rets = returns_by_symbol.get(a.symbol)
        if rets is not None and recent_volatility(rets) > settings.vol_skip_threshold:
            skips.append(f"{a.name}: high volatility")
            continue

        ceiling = (a.target_weight + settings.drift_threshold) * total_equity
        trim_value = a.deployed_value - ceiling

        # correlation offset: if an underweight strategy shares this symbol's cluster,
        # its deficit reduces the effective overweight to be trimmed.
        cluster = next((c for c in clusters if a.symbol in c), {a.symbol})
        offset = sum(-under_by_symbol[s].drift * total_equity
                     for s in cluster if s in under_by_symbol)
        trim_value = max(0.0, trim_value - offset)

        if trim_value < min_trim_notional or trim_value <= 0:
            skips.append(f"{a.name}: below fee/benefit floor")
            continue

        price = prices.get(a.symbol, 0.0)
        if price <= 0:
            skips.append(f"{a.name}: no price")
            continue
        trims.append(TrimAction(name=a.name, symbol=a.symbol,
                                qty=trim_value / price, value=trim_value,
                                reason=f"drift {a.drift:.3f} > {settings.drift_threshold}"))
    return trims, skips
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_rebalance.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/rebalance.py tests/test_rebalance.py
git commit -m "feat(rebalance): plan_trims with vol/correlation/fee guards"
```

---

### Task 4: `Rebalancer` orchestrator (min-interval + mode dispatch)

**Files:**
- Modify: `src/swingbot/rebalance.py`
- Test: `tests/test_rebalance.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `class Rebalancer(settings, state)` with `evaluate(now, total_equity, deployed, symbols, targets, prices, returns_by_symbol) -> RebalanceResult` and `mark_ran(now)`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_rebalance.py
from datetime import datetime, timezone, timedelta
from swingbot.rebalance import Rebalancer, RebalanceState

def _now():
    return datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)

def test_evaluate_min_interval_skips():
    st = RebalanceState(last_rebalance_at=_now().isoformat())
    r = Rebalancer(RebalanceSettings(enabled=True, mode="hard",
                                     min_interval_minutes=60), st)
    res = r.evaluate(now=_now() + timedelta(minutes=30), total_equity=10_000.0,
                     deployed={"a": 5_000.0}, symbols={"a": "BTC/USD"},
                     targets={"a": 0.3}, prices={"BTC/USD": 100.0},
                     returns_by_symbol={})
    assert res.ran is False
    assert "interval" in res.skipped_reason

def test_evaluate_soft_mode_returns_no_trims():
    r = Rebalancer(RebalanceSettings(enabled=True, mode="soft"), RebalanceState())
    res = r.evaluate(now=_now(), total_equity=10_000.0, deployed={"a": 5_000.0},
                     symbols={"a": "BTC/USD"}, targets={"a": 0.3},
                     prices={"BTC/USD": 100.0}, returns_by_symbol={})
    assert res.ran is True
    assert res.trims == []
    assert res.mode == "soft"

def test_evaluate_hard_mode_emits_trim():
    import pandas as pd
    rets = {"BTC/USD": pd.Series([1, 2, 3, 4, 5]).pct_change().dropna()}
    r = Rebalancer(RebalanceSettings(enabled=True, mode="hard", vol_skip_threshold=1.0,
                                     fee_rate=0.0, benefit_factor=0.0), RebalanceState())
    res = r.evaluate(now=_now(), total_equity=10_000.0, deployed={"a": 5_000.0},
                     symbols={"a": "BTC/USD"}, targets={"a": 0.3},
                     prices={"BTC/USD": 100.0}, returns_by_symbol=rets)
    assert res.ran is True
    assert len(res.trims) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_rebalance.py -k evaluate -v`
Expected: FAIL with `ImportError: cannot import name 'Rebalancer'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/swingbot/rebalance.py
from datetime import datetime, timedelta


class Rebalancer:
    """Pure rebalancing logic over a mutable RebalanceState. No IO."""

    def __init__(self, settings: "RebalanceSettings", state: "RebalanceState"):
        self.settings = settings
        self.state = state

    def _interval_ok(self, now: datetime) -> bool:
        if not self.state.last_rebalance_at:
            return True
        last = datetime.fromisoformat(self.state.last_rebalance_at)
        return now - last >= timedelta(minutes=self.settings.min_interval_minutes)

    def mark_ran(self, now: datetime) -> None:
        self.state.last_rebalance_at = now.isoformat()

    def evaluate(self, *, now, total_equity, deployed, symbols, targets,
                 prices, returns_by_symbol) -> "RebalanceResult":
        allocs = compute_allocations(deployed, symbols, targets, total_equity)
        if not self._interval_ok(now):
            return RebalanceResult(False, "min interval not elapsed", allocs, [],
                                   self.settings.mode)
        if self.settings.mode != "hard":
            return RebalanceResult(True, "", allocs, [], "soft")
        drifted = detect_drift(allocs, self.settings.drift_threshold)
        trims, _skips = plan_trims(drifted, allocs, prices, total_equity,
                                   self.settings, returns_by_symbol)
        return RebalanceResult(True, "", allocs, trims, "hard")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_rebalance.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/rebalance.py tests/test_rebalance.py
git commit -m "feat(rebalance): Rebalancer evaluate with interval + mode dispatch"
```

---

### Task 5: Persist targets + settings in `ProfileStore`

**Files:**
- Modify: `src/swingbot/profiles.py` (after `set_portfolio_settings`, ~L157)
- Test: `tests/test_profiles.py` (create if absent)

**Interfaces:**
- Produces: `ProfileStore.get_rebalance_settings() -> dict`, `set_rebalance_settings(dict)` (merge), `get_rebalance_targets() -> dict`, `set_rebalance_targets(dict)` (validated: weights ∈[0,1], sum ≤ 1.0).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_profiles.py  (append if file exists)
import pytest
from swingbot.profiles import ProfileStore

def test_rebalance_settings_round_trip_and_merge(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    s.set_rebalance_settings({"enabled": True, "mode": "hard"})
    s.set_rebalance_settings({"drift_threshold": 0.1})   # merge, not replace
    got = s.get_rebalance_settings()
    assert got["enabled"] is True and got["mode"] == "hard"
    assert got["drift_threshold"] == 0.1

def test_rebalance_targets_round_trip(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    s.set_rebalance_targets({"a": 0.3, "b": 0.4})
    assert s.get_rebalance_targets() == {"a": 0.3, "b": 0.4}

def test_rebalance_targets_reject_sum_over_one(tmp_path):
    s = ProfileStore(str(tmp_path / "p.db"))
    with pytest.raises(ValueError):
        s.set_rebalance_targets({"a": 0.7, "b": 0.5})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_profiles.py -k rebalance -v`
Expected: FAIL with `AttributeError: 'ProfileStore' object has no attribute 'set_rebalance_settings'`

- [ ] **Step 3: Write minimal implementation**

```python
# add to src/swingbot/profiles.py (import json at top is already present)
    def get_rebalance_settings(self) -> dict:
        raw = self.get_meta("rebalance_settings")
        return json.loads(raw) if raw else {}

    def set_rebalance_settings(self, settings: dict) -> None:
        merged = self.get_rebalance_settings()
        merged.update(settings)
        self.set_meta("rebalance_settings", json.dumps(merged))

    def get_rebalance_targets(self) -> dict:
        raw = self.get_meta("rebalance_targets")
        return json.loads(raw) if raw else {}

    def set_rebalance_targets(self, targets: dict) -> None:
        for name, w in targets.items():
            if not (0.0 <= float(w) <= 1.0):
                raise ValueError(f"weight for {name} out of [0,1]: {w}")
        if sum(float(w) for w in targets.values()) > 1.0 + 1e-9:
            raise ValueError("target weights sum to more than 1.0")
        self.set_meta("rebalance_targets", json.dumps(targets))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_profiles.py -k rebalance -v`
Expected: PASS (3 tests). Confirm `import json` exists at top of `profiles.py`; if not, add it.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/profiles.py tests/test_profiles.py
git commit -m "feat(rebalance): persist targets + settings in ProfileStore meta"
```

---

### Task 6: Persist `RebalanceState` in `StateStore`

**Files:**
- Modify: `src/swingbot/state.py` (table creation ~L37; methods near `load_portfolio_risk_state` ~L198)
- Test: `tests/test_state.py` (append)

**Interfaces:**
- Consumes: `RebalanceState` (Task 1).
- Produces: `StateStore.save_rebalance_state(rs: RebalanceState)`, `load_rebalance_state() -> RebalanceState`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state.py (append)
from swingbot.state import StateStore
from swingbot.rebalance import RebalanceState

def test_rebalance_state_round_trip(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    s.save_rebalance_state(RebalanceState(last_rebalance_at="2026-06-19T12:00:00+00:00"))
    got = s.load_rebalance_state()
    assert got.last_rebalance_at == "2026-06-19T12:00:00+00:00"

def test_rebalance_state_default_when_empty(tmp_path):
    s = StateStore(str(tmp_path / "s.db"))
    assert s.load_rebalance_state().last_rebalance_at == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_state.py -k rebalance_state -v`
Expected: FAIL with `AttributeError: ... 'save_rebalance_state'`

- [ ] **Step 3: Write minimal implementation**

In `__init__` table creation block (next to the `portfolio_risk` CREATE at ~L37) add:
```python
                "CREATE TABLE IF NOT EXISTS rebalance_state (id INTEGER PRIMARY KEY, data TEXT)")
```
Then add methods (near `load_portfolio_risk_state`), importing `RebalanceState` from `swingbot.rebalance` at top:
```python
    def save_rebalance_state(self, rs: "RebalanceState") -> None:
        import json
        from dataclasses import asdict
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO rebalance_state (id, data) VALUES (1, ?)",
                (json.dumps(asdict(rs)),))
            self._conn.commit()

    def load_rebalance_state(self) -> "RebalanceState":
        import json
        from swingbot.rebalance import RebalanceState
        row = self._conn.execute(
            "SELECT data FROM rebalance_state WHERE id=1").fetchone()
        if not row:
            return RebalanceState()
        return RebalanceState(**json.loads(row[0]))
```
NOTE: match the existing locking/commit idiom in `state.py` (check how `save_portfolio_risk_state` guards `self._conn`); use the same pattern rather than the `self._lock` shown above if it differs.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_state.py -k rebalance_state -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/state.py tests/test_state.py
git commit -m "feat(rebalance): persist RebalanceState in StateStore"
```

---

### Task 7: Telemetry — `rebalance_events`

**Files:**
- Modify: `src/swingbot/telemetry.py`
- Test: `tests/test_telemetry.py` (append)

**Interfaces:**
- Produces: `TelemetryStore.record_rebalance(*, ts, mode, ran, skipped_reason, allocations_json, trims_json)`; `recent_rebalance(limit=50) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_telemetry.py (append)
from swingbot.telemetry import TelemetryStore

def test_record_and_read_rebalance_event(tmp_path):
    t = TelemetryStore(str(tmp_path / "t.db"))
    t.record_rebalance(ts="2026-06-19T12:00:00+00:00", mode="hard", ran=True,
                       skipped_reason="", allocations_json="[]", trims_json="[]")
    rows = t.recent_rebalance(limit=10)
    assert len(rows) == 1
    assert rows[0]["mode"] == "hard" and rows[0]["ran"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_telemetry.py -k rebalance -v`
Expected: FAIL with `AttributeError: ... 'record_rebalance'`

- [ ] **Step 3: Write minimal implementation**

In `__init__`, add a table next to `cycle_records`:
```python
                """
                CREATE TABLE IF NOT EXISTS rebalance_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT, mode TEXT, ran INTEGER,
                    skipped_reason TEXT, allocations TEXT, trims TEXT
                )
                """
```
Add methods:
```python
    def record_rebalance(self, *, ts, mode, ran, skipped_reason,
                         allocations_json, trims_json) -> None:
        self._conn.execute(
            "INSERT INTO rebalance_events "
            "(ts, mode, ran, skipped_reason, allocations, trims) "
            "VALUES (?,?,?,?,?,?)",
            (ts, mode, 1 if ran else 0, skipped_reason, allocations_json, trims_json))
        self._conn.commit()
        self._conn.execute(
            "DELETE FROM rebalance_events WHERE id NOT IN "
            "(SELECT id FROM rebalance_events ORDER BY id DESC LIMIT ?)",
            (self.retention,))
        self._conn.commit()

    def recent_rebalance(self, limit: int = 50) -> list:
        rows = self._conn.execute(
            "SELECT ts, mode, ran, skipped_reason, allocations, trims "
            "FROM rebalance_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"ts": r[0], "mode": r[1], "ran": bool(r[2]),
                 "skipped_reason": r[3], "allocations": r[4], "trims": r[5]}
                for r in rows]
```
NOTE: match the existing connection/lock idiom used by `record()` in this file.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_telemetry.py -k rebalance -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/telemetry.py tests/test_telemetry.py
git commit -m "feat(rebalance): telemetry rebalance_events table"
```

---

### Task 8: Orchestrator soft-sizing hook (`sizing_equity`)

**Files:**
- Modify: `src/swingbot/orchestrator.py` (`tick` L81-93, `_maybe_enter` L121-165)
- Test: `tests/test_orchestrator.py` (append)

**Interfaces:**
- Produces: `Orchestrator.tick(now=None, sizing_equity: float | None = None)`; when `sizing_equity` is given it is used for `risk.size(...)` only; `risk.start_day`, the gate, and daily-loss math keep using real `acct["equity"]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_orchestrator.py (append). Reuse the file's existing FakeBroker/FakeData
# fixtures that already drive a full entry. Build an orchestrator that WILL enter,
# then assert the sized qty halves when sizing_equity is half of equity.
def test_sizing_equity_override_scales_position(make_entering_orchestrator):
    orch_full = make_entering_orchestrator(equity=10_000.0)
    full = orch_full.tick()                       # sizes off 10_000
    orch_half = make_entering_orchestrator(equity=10_000.0)
    half = orch_half.tick(sizing_equity=5_000.0)  # sizes off 5_000
    assert half.detail["qty"] == full.detail["qty"] / 2
```

If no such fixture exists, add a minimal `make_entering_orchestrator` helper in the test mirroring the existing `FakeBroker`/`FakeData` setup in `test_orchestrator.py`, with a profile whose signals always pass, and have `_submit_exit`/entry expose the sized `qty` in `DecisionResult.detail`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_orchestrator.py -k sizing_equity -v`
Expected: FAIL — `tick()` takes no `sizing_equity` kwarg.

- [ ] **Step 3: Write minimal implementation**

```python
# orchestrator.py — change tick signature + threading
    def tick(self, now: datetime | None = None,
             sizing_equity: float | None = None) -> DecisionResult:
        now = now or datetime.now(timezone.utc)
        acct = self.broker.get_account()
        self.risk.start_day(now=now, equity=acct["equity"])
        self.state.save_risk_state(self.risk.state)

        pending = self.state.load_pending_order()
        if pending is not None:
            return self._pending_result(pending)
        pos = self.state.load_position()
        if pos is not None:
            return self._manage_open(pos, now)
        return self._maybe_enter(now, acct["equity"], sizing_equity)
```
```python
# _maybe_enter signature + the size call (L121, L165)
    def _maybe_enter(self, now: datetime, equity: float,
                     sizing_equity: float | None = None) -> DecisionResult:
        ...
        qty = self.risk.size(equity=(sizing_equity if sizing_equity is not None else equity),
                             entry_price=price, stop_price=stop)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_orchestrator.py -v`
Expected: PASS (new test + all existing orchestrator tests unchanged — `sizing_equity` defaults to None).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(rebalance): orchestrator sizing_equity override hook"
```

---

### Task 9: Supervisor wiring — build + soft sizing + soft cap

**Files:**
- Modify: `src/swingbot/supervisor.py` (`build` ~L250-289, `_make_gate` ~L292-310, `tick_all` ~L347-450)
- Test: `tests/test_supervisor.py` (append)

**Interfaces:**
- Consumes: `Rebalancer`, `RebalanceSettings`, `allocated_equity` (Tasks 1/4), ProfileStore + StateStore helpers (Tasks 5/6).
- Produces: `self._rebalancer`, `self._rebalance_settings`, `self._rebalance_targets`; `tick_all` passes per-strategy `sizing_equity` to `orch.tick`; `_make_gate` enforces a per-strategy allocated-equity ceiling. All gated on `settings.enabled` — when False, behavior is unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_supervisor.py (append). Use the file's existing supervisor harness.
def test_soft_sizing_passes_allocated_equity(monkeypatch, built_supervisor_two_strats):
    sup = built_supervisor_two_strats(enabled=True, mode="soft",
                                      targets={"a": 0.3, "b": 0.3}, equity=10_000.0)
    captured = {}
    for name, s in sup._strategies.items():
        orig = s["orch"].tick
        s["orch"].tick = lambda now=None, sizing_equity=None, _n=name: (
            captured.__setitem__(_n, sizing_equity))
    sup.tick_all()
    assert captured["a"] == 3_000.0      # 0.3 * 10_000
    assert captured["b"] == 3_000.0

def test_soft_sizing_disabled_passes_none(built_supervisor_two_strats):
    sup = built_supervisor_two_strats(enabled=False, targets={}, equity=10_000.0)
    captured = {}
    for name, s in sup._strategies.items():
        s["orch"].tick = lambda now=None, sizing_equity=None, _n=name: (
            captured.__setitem__(_n, sizing_equity))
    sup.tick_all()
    assert captured["a"] is None and captured["b"] is None
```

If `built_supervisor_two_strats` does not exist, add a fixture building a `PortfolioSupervisor` with two fake strategies (mirror existing supervisor tests / `FakeBroker` returning the given equity, two `StrategyProfile`s, settings/targets written into the `ProfileStore`).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_supervisor.py -k soft_sizing -v`
Expected: FAIL — `tick_all` does not pass `sizing_equity`.

- [ ] **Step 3: Write minimal implementation**

In `build()` after constructing portfolio risk:
```python
        from swingbot.rebalance import Rebalancer, RebalanceSettings
        self._rebalance_settings = RebalanceSettings(
            **self.profiles.get_rebalance_settings())
        self._rebalance_targets = self.profiles.get_rebalance_targets()
        self._rebalancer = Rebalancer(self._rebalance_settings,
                                      self._store.load_rebalance_state())
```
In `tick_all`, where each strategy's `orch.tick(...)` is called inside the loop, compute and pass `sizing_equity`:
```python
        from swingbot.rebalance import allocated_equity
        n = len(self._strategies)
        for name in sorted(self._strategies):
            s = self._strategies[name]
            sizing_equity = None
            if self._rebalance_settings.enabled:
                sizing_equity = allocated_equity(
                    name, self._rebalance_targets, acct["equity"], n)
            result = s["orch"].tick(now=now, sizing_equity=sizing_equity)
            ...
```
In `_make_gate`, after computing `deployed` and `equity`, add the per-strategy ceiling when enabled (use the strategy `name` captured by the closure — pass `name` into `_make_gate`):
```python
            if self._rebalance_settings.enabled:
                n = len(self._strategies)
                alloc = allocated_equity(name, self._rebalance_targets, equity, n)
                strat_deployed = self._strategy_deployed_value(name)  # helper: this strat only
                if strat_deployed + prospective_value > alloc:
                    return PortfolioDecision(
                        False, f"rebalance soft cap: {strat_deployed + prospective_value:.2f} "
                               f"> allocated {alloc:.2f}")
```
Add a small helper `_strategy_deployed_value(name)` summing that one strategy's open position + pending-buy value (reuse the existing deployed-computation loop, filtered to `name`). Keep all of this behind `if self._rebalance_settings.enabled:` so `enabled=False` is byte-for-byte unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_supervisor.py -v`
Expected: PASS (new + existing supervisor tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor.py
git commit -m "feat(rebalance): supervisor build wiring + soft sizing + soft cap"
```

---

### Task 10: Supervisor hard-trim step + safety gates + telemetry

**Files:**
- Modify: `src/swingbot/supervisor.py` (`tick_all`, after the strategy loop)
- Test: `tests/test_supervisor.py` (append)

**Interfaces:**
- Consumes: `self._rebalancer.evaluate`, broker sell, `_portfolio_risk.state`, `TelemetryStore.record_rebalance`.
- Produces: `_run_rebalance(now, acct)` called at the end of `tick_all`; places reduce-only sells for hard-mode trims; logs every evaluation; updates `RebalanceState`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_supervisor.py (append)
def test_hard_mode_trims_overweight_and_records(built_supervisor_two_strats, fake_sells):
    # strat "a" deployed 5_000 of 10_000 equity, target 0.3 -> trims ~1_500 worth
    sup = built_supervisor_two_strats(enabled=True, mode="hard",
                                      targets={"a": 0.3, "b": 0.3}, equity=10_000.0,
                                      deployed={"a": 5_000.0, "b": 0.0},
                                      prices={"BTC/USD": 100.0}, low_vol=True,
                                      fee_rate=0.0)
    sup.tick_all()
    assert fake_sells, "expected a reduce-only sell for overweight strat a"
    assert sup._telemetry.recent_rebalance(10)[0]["mode"] == "hard"

def test_portfolio_kill_switch_suppresses_all_trims(built_supervisor_two_strats, fake_sells):
    sup = built_supervisor_two_strats(enabled=True, mode="hard",
                                      targets={"a": 0.3}, equity=10_000.0,
                                      deployed={"a": 5_000.0}, prices={"BTC/USD": 100.0})
    sup._portfolio_risk.state.kill_switch_active = True
    sup.tick_all()
    assert fake_sells == []
    assert "kill switch" in sup._telemetry.recent_rebalance(10)[0]["skipped_reason"]
```

Add `fake_sells` fixture capturing broker sell calls; extend `built_supervisor_two_strats` to accept `mode/deployed/prices/low_vol/fee_rate`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_supervisor.py -k "hard_mode or kill_switch_suppress" -v`
Expected: FAIL — no rebalance step exists.

- [ ] **Step 3: Write minimal implementation**

```python
# supervisor.py — call at the very end of tick_all(), after the strategy loop:
        if self._rebalance_settings.enabled:
            self._run_rebalance(now, acct)
```
```python
    def _run_rebalance(self, now, acct) -> None:
        import json
        from dataclasses import asdict
        equity = acct["equity"]

        # SAFETY: portfolio kill switch / circuit breaker suppresses everything.
        if self._portfolio_risk.state.kill_switch_active:
            self._telemetry.record_rebalance(
                ts=now.isoformat(), mode=self._rebalance_settings.mode, ran=False,
                skipped_reason=f"portfolio kill switch: "
                               f"{self._portfolio_risk.state.kill_switch_reason}",
                allocations_json="[]", trims_json="[]")
            return

        deployed, symbols, prices, returns = {}, {}, {}, {}
        for name in sorted(self._strategies):
            s = self._strategies[name]
            # SAFETY: never trim a strategy whose own kill switch is active.
            if self._strategy_kill_active(name):
                continue
            deployed[name] = self._strategy_deployed_value(name)
            symbols[name] = s["profile"].symbol
            sym = s["profile"].symbol
            price = self._broker.get_latest_price(sym)
            prices[sym] = price
            returns[sym] = self._recent_returns(sym, self._rebalance_settings.vol_lookback)

        res = self._rebalancer.evaluate(
            now=now, total_equity=equity, deployed=deployed, symbols=symbols,
            targets=self._rebalance_targets, prices=prices, returns_by_symbol=returns)

        if res.ran and res.mode == "hard":
            for trim in res.trims:
                # reduce-only SELL on the configured paper/live mode path
                self._broker.submit_sell(trim.symbol, trim.qty)   # match real broker API
                self._reduce_stored_position(trim.name, trim.qty)
            self._rebalancer.mark_ran(now)
            self._store.save_rebalance_state(self._rebalancer.state)

        self._telemetry.record_rebalance(
            ts=now.isoformat(), mode=res.mode, ran=res.ran,
            skipped_reason=res.skipped_reason,
            allocations_json=json.dumps([asdict(a) for a in res.allocations]),
            trims_json=json.dumps([asdict(t) for t in res.trims]))
```
Implement the helpers against the real broker/state APIs:
- `_strategy_kill_active(name)` — read that strategy's `RiskState.kill_switch_active` via its state view.
- `_recent_returns(symbol, lookback)` — pull recent closes via the supervisor's market/cached provider and return `closes` as a `pd.Series` (so `recent_volatility`/`correlation_clusters` work). If unavailable, return an empty Series (guards treat as zero vol).
- `submit_sell` / `_reduce_stored_position` — use the broker's existing market-sell + the orchestrator's position-shrink path (check `broker/base.py` and how `_submit_exit` reduces qty); the remainder must keep its existing stop, managed normally next tick.
- Confirm the trim is **reduce-only** and routes through `self.mode` exactly like an exit order.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_supervisor.py -v`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor.py
git commit -m "feat(rebalance): hard-mode trim step with kill-switch/paper-live safety"
```

---

### Task 11: API endpoints

**Files:**
- Modify: `src/swingbot/web.py`
- Test: `tests/test_web.py` (append)

**Interfaces:**
- Produces: `GET /api/rebalance/status`, `GET|POST /api/rebalance/settings`, `GET|POST /api/rebalance/targets`, `POST /api/rebalance/run`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web.py (append). Use the existing FastAPI TestClient fixture.
def test_get_rebalance_settings_defaults(client):
    r = client.get("/api/rebalance/settings")
    assert r.status_code == 200
    assert r.json()["enabled"] is False

def test_post_rebalance_targets_validates_sum(client):
    r = client.post("/api/rebalance/targets", json={"targets": {"a": 0.7, "b": 0.5}})
    assert r.status_code == 400

def test_get_rebalance_status_shape(client):
    r = client.get("/api/rebalance/status")
    assert r.status_code == 200
    body = r.json()
    assert "allocations" in body and "mode" in body and "last_rebalance_at" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_web.py -k rebalance -v`
Expected: FAIL with 404s.

- [ ] **Step 3: Write minimal implementation**

Add routes to `web.py` mirroring the existing portfolio-settings routes (same auth/token gate, same `profiles`/`supervisor` accessors used by current endpoints):
```python
@app.get("/api/rebalance/settings")
def get_rebalance_settings():
    from swingbot.rebalance import RebalanceSettings
    return {**asdict(RebalanceSettings()), **profiles.get_rebalance_settings()}

@app.post("/api/rebalance/settings")
def set_rebalance_settings(body: dict):
    profiles.set_rebalance_settings(body)
    return {"ok": True}

@app.get("/api/rebalance/targets")
def get_rebalance_targets():
    return {"targets": profiles.get_rebalance_targets()}

@app.post("/api/rebalance/targets")
def set_rebalance_targets(body: dict):
    try:
        profiles.set_rebalance_targets(body.get("targets", {}))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}

@app.get("/api/rebalance/status")
def rebalance_status():
    # supervisor exposes a read-only snapshot of last allocations/mode/timing
    return supervisor.rebalance_status()

@app.post("/api/rebalance/run")
def rebalance_run():
    return supervisor.run_rebalance_now()   # honors all guards + paper/live gate
```
Add `PortfolioSupervisor.rebalance_status()` (build allocations from current deployed/targets without placing orders) and `run_rebalance_now()` (calls `_run_rebalance(datetime.now(UTC), acct)` and returns the result dict). Match `web.py`'s existing import style (`asdict`, `HTTPException`) and how it references the live `profiles`/`supervisor` singletons.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_web.py -k rebalance -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/web.py src/swingbot/supervisor.py tests/test_web.py
git commit -m "feat(rebalance): API endpoints for settings/targets/status/run"
```

---

### Task 12: Dashboard rebalance panel

**Files:**
- Create: `frontend/src/components/RebalancePanel.jsx`
- Modify: `frontend/src/pages/Settings.jsx` (mount the panel) and `frontend/src/api.js` (add calls)
- Test: manual + `npm run build`

**Interfaces:**
- Consumes: the Task 11 endpoints.
- Produces: allocation table (target/actual/drift bars), enable + soft/hard toggles, threshold/interval/fee inputs, editable targets with "sums to X%" validation, last/next rebalance + skip reason, "Rebalance now" button (disabled unless enabled & hard).

- [ ] **Step 1: Add API helpers**

In `frontend/src/api.js`, following the existing `api` object pattern:
```javascript
  getRebalanceStatus: () => get("/api/rebalance/status"),
  getRebalanceSettings: () => get("/api/rebalance/settings"),
  setRebalanceSettings: (b) => post("/api/rebalance/settings", b),
  getRebalanceTargets: () => get("/api/rebalance/targets"),
  setRebalanceTargets: (b) => post("/api/rebalance/targets", b),
  runRebalance: () => post("/api/rebalance/run", {}),
```

- [ ] **Step 2: Build `RebalancePanel.jsx`**

A component that loads status+settings+targets on mount (poll every ~10s like other panels), renders the allocation table with per-row over/under bars, the controls bound to `setRebalanceSettings`/`setRebalanceTargets`, a live sum indicator that blocks save when `sum > 1.0`, and a "Rebalance now" button wired to `runRebalance` (disabled unless `enabled && mode==='hard'`). Reuse existing component/styling conventions from neighboring panels (e.g. the autodash panels).

- [ ] **Step 3: Mount it**

Import and render `<RebalancePanel />` inside `Settings.jsx` (or a new "Rebalance" section), following how existing sections are laid out.

- [ ] **Step 4: Build the frontend**

Run: `cd frontend && npm run build`
Expected: build succeeds, no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/RebalancePanel.jsx frontend/src/pages/Settings.jsx frontend/src/api.js
git commit -m "feat(rebalance): dashboard rebalance panel"
```

---

### Task 13: Integration test, full gate, docker rebuild, roadmap update

**Files:**
- Test: `tests/test_rebalance_integration.py`
- Modify: `docs/ROADMAP_STATUS.md`

- [ ] **Step 1: Write an end-to-end integration test**

Drive `PortfolioSupervisor.tick_all` with `FakeBroker`/`FakeData` (as in `test_orchestrator.py`/`test_supervisor.py`) through three scenarios:
1. `enabled=False` → no `sizing_equity`, no trims, no rebalance telemetry rows (regression: unchanged behavior).
2. `enabled=True, mode="soft"` → each strategy sized off `allocated_equity`; soft cap blocks an overweight entry; still no sells.
3. `enabled=True, mode="hard"` with an overweight strategy and low vol → exactly one reduce-only sell to just under the band; a `rebalance_events` row with `ran=True, mode="hard"`.

```python
def test_end_to_end_soft_then_hard(...):
    # build supervisor, set targets, run tick_all in each mode, assert per above
    ...
```

- [ ] **Step 2: Run the full backend gate**

Run: `.venv/bin/pytest -q && .venv/bin/ruff check src tests`
Expected: all green (existing 598 + new tests), ruff clean.

- [ ] **Step 3: Build frontend gate**

Run: `cd frontend && npm run build`
Expected: green.

- [ ] **Step 4: Docker rebuild + restart (standing rule)**

Run: `docker compose build swingbot && docker compose up -d swingbot`
Then verify: `curl -s localhost:8000/api/rebalance/settings` returns `{"enabled": false, ...}` and the dashboard panel renders.

- [ ] **Step 5: Update roadmap + commit**

Update `docs/ROADMAP_STATUS.md` NEXT ACTION to record the rebalancing layer shipped (off by default, soft/hard modes, guards, API + panel), then:
```bash
git add docs/ROADMAP_STATUS.md tests/test_rebalance_integration.py
git commit -m "feat(rebalance): e2e integration test + roadmap update"
```

---

## Self-Review

**Spec coverage:** §3 decisions → Tasks 1–4/9/10; configurable targets in SQLite → Task 5; drift detection + threshold → Tasks 2/4; soft mode (sizing) → Tasks 8/9; hard mode (trim) → Task 10; smart timing (vol/correlation/fee/interval) → Tasks 2/3/4; supervisor + sizing integration → Tasks 8/9/10; API → Task 11; dashboard → Task 12; never violate kill switches/breakers, never force entries, paper/live, telemetry → Task 10 safety gates + Task 7; rollout-off regression → Tasks 9/13. All spec sections covered.

**Placeholder scan:** Code-bearing steps carry real code. Tasks 10–12 contain explicit "match the real broker/state/web API" notes rather than invented signatures (broker sell, position-shrink, web singletons) — these are deliberate integration anchors the implementer verifies against the named files, not vague TODOs.

**Type consistency:** `RebalanceSettings`/`StrategyAllocation`/`TrimAction`/`RebalanceResult`/`RebalanceState` and `evaluate(...)`/`plan_trims(...)`/`allocated_equity(...)` signatures are consistent across Tasks 1–11. `sizing_equity` kwarg name matches between Tasks 8 and 9. Store helper names (`get/set_rebalance_settings/targets`, `save/load_rebalance_state`, `record_rebalance/recent_rebalance`) are consistent across Tasks 5–11.
