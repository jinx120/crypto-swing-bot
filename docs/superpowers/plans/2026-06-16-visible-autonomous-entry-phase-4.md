# Visible Autonomous Entry — Phase 4 (Managed Strategies + Optional Proof-of-Life) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add honest EMA-based managed trend strategies (`btc_trend`, `eth_trend`), a versioned managed-profile reconciler that never deletes or overwrites user profiles (backing up first), and an opt-in, clearly-separated `paper_probe` proof-of-life profile.

**Architecture:** Pure managed-profile *definitions* (data) plus a *reconciler* that seeds/upgrades only managed-origin profiles, backs up the full profile set before any write, and arms the managed strategies. A new EMA indicator powers an `ema_trend` signal. The probe is a separate deterministic `paper_probe` signal, gated by `SWINGBOT_ENABLE_PAPER_PROBE=1` **and** `mode == "paper"`, fired at most once via a durable `ProbeMarkerStore`. The supervisor calls the reconciler at build time.

**Tech Stack:** Python 3.11, pandas, SQLite (`sqlite3`), FastAPI (existing), pytest, ruff.

---

## Context for a cold code-gen agent

You are implementing Phase 4 of an existing, working project (`crypto-swing-bot`). Phases 0–3 are done and on `master`. **Do not redesign anything; implement the tasks below verbatim, TDD, one task at a time.**

### House rules (non-negotiable)
- **Python venv:** use **`.venv/bin/python`** — plain `python`/`pytest` are NOT on PATH. Run tests with `.venv/bin/python -m pytest -q`.
- **Lint:** run `.venv/bin/python -m ruff check src/` before every commit; it must be clean.
- **TDD:** for every task write the failing test first, watch it fail, implement the minimum, watch it pass, then commit.
- **Commit + push per task.** After each task's tests are green and ruff is clean, commit AND push to `origin/master`. Pull from `origin/master` before starting work and whenever a push is rejected. Never leave work only on the local clone.
- **Scope discipline:** only touch the files named in each task's **Files** block. The working tree may carry unrelated uncommitted FVG/preset/graphify work — **do not stage or modify it.** Use `git add <explicit paths>` (never `git add -A`).
- Do not claim live Alpaca/container behavior. Phase 4 is unit/integration only; the live wiring is exercised in Phase 6.

### Current code state you build on (already exists)
- `src/swingbot/indicators.py` — has `rsi`, `atr`, `rolling_vwap`, `sma`, `lookback_return`. **No `ema` yet** (Task 1 adds it).
- `src/swingbot/signals/base.py` — `Signal` Protocol: attributes `name: str`, `weight: float`, method `evaluate(ctx: MarketContext) -> SignalResult`.
- Example signal `src/swingbot/signals/oversold.py` — the pattern to copy: a class with a class-level `name`, an `__init__(self, weight, ...)`, and `evaluate` returning `SignalResult(self.name, score, meta)`.
- `src/swingbot/confluence.py` — `_REGISTRY` maps signal-name → class; `build_signals(profile)` instantiates `cls(**params)` for each `profile.signals[name]` params dict (which must include `"weight"`). New signals MUST be registered here.
- `src/swingbot/types.py` — `MarketContext(candles, benchmark, htf)`, `SignalResult(name, score, meta)`, `Regime` enum (`UPTREND`/`NEUTRAL`/`DOWNTREND`), `DecisionCode` enum (includes `ENTERED`, `EXITED`). Candle DataFrames have columns `ts, open, high, low, close, volume`, ascending; the **last row is the most recent closed bar**.
- `src/swingbot/profile.py` — `StrategyProfile` dataclass + `from_dict`. `allowed_regimes` is a tuple of `Regime`; in a profile **dict** it is a list of strings like `["uptrend","neutral"]` (from_dict converts).
- `src/swingbot/profiles.py` — `ProfileStore` (SQLite). Relevant methods: `save(name, dict)` (validates via `StrategyProfile.from_dict`), `get(name) -> dict|None`, `list() -> list[str]`, `delete(name)`, `arm(name)`, `disarm(name)`, `is_armed(name)`, `list_armed()`. Has a `meta(key, value)` table used by `set_active`/portfolio settings. Task 5 adds generic `get_meta`/`set_meta`.
- `src/swingbot/supervisor.py` — `PortfolioSupervisor(profiles, creds, state_db, market=..., broker=..., mode="paper", runtime_state=...)`. `build()` reads `self.profiles.list_armed()`, loads each profile dict, and constructs one `Orchestrator` per armed strategy. `tick_all(now)` runs them. `self.mode` is `"paper"` or `"live"`.
- `src/swingbot/webmain.py` — composition root; constructs `ProfileStore`, `PortfolioSupervisor`, etc. with `DATA_DIR = os.environ.get("SWINGBOT_DATA_DIR", "~/.swingbot")`.
- `src/swingbot/orchestrator.py` — `Orchestrator.tick()` returns a `DecisionResult`; entry path is `_maybe_enter`. It evaluates regime → confluence → ATR → sizing → portfolio gate → order. The probe relies on this exact pipeline (so it must NOT bypass it).

### What "managed" means here
- A profile is **managed-origin** iff its name is in `MANAGED_PROFILE_NAMES` (Task 3). Everything else is a **user profile** and must never be deleted or overwritten by the reconciler.
- Managed strategy profiles: `btc_trend`, `eth_trend` (always present). Managed probe profile: `paper_probe` (present only when `SWINGBOT_ENABLE_PAPER_PROBE=1` and `mode == "paper"`).

### Success criteria for this phase (from spec §5 Phase 4 + §7)
1. EMA indicator exists with tests.
2. `btc_trend`/`eth_trend` are honest EMA trend definitions, reproducible (same dict every call).
3. Reconciliation is versioned, backs up the full profile set before any change, and **never deletes/overwrites user profiles** (spec §7.9).
4. The `paper_probe` is opt-in, rejected when `mode != "paper"`, fires at most once (durable marker), and is clearly separated/labeled as a probe — not a trading strategy (spec §3.4, §7.10).
5. Managed-canvas server-side mutation enforcement is **explicitly out of scope** (deferred; spec §5 item 5 is conditional on a mode we are not adopting now).
6. `pytest -q` and `cd frontend && npm run build` stay green.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/swingbot/indicators.py` | add `ema()` | Modify |
| `src/swingbot/signals/ema_trend.py` | `EmaTrendSignal` (honest EMA crossover) | Create |
| `src/swingbot/signals/paper_probe.py` | `PaperProbeSignal` (deterministic proof-of-life) | Create |
| `src/swingbot/confluence.py` | register `ema_trend`, `paper_probe` | Modify |
| `src/swingbot/managed_profiles.py` | definitions, version, names, labels, backup, **reconciler** | Create |
| `src/swingbot/probe_marker.py` | `ProbeMarkerStore` + `probe_should_fire` | Create |
| `src/swingbot/profiles.py` | generic `get_meta`/`set_meta` | Modify |
| `src/swingbot/supervisor.py` | call reconciler at build; mark probe complete on terminal entry | Modify |
| `src/swingbot/webmain.py` | wire reconciler inputs (env, backup dir, marker store) | Modify |
| `tests/test_indicators.py` | EMA tests | Modify |
| `tests/test_signals.py` | `ema_trend` tests | Modify |
| `tests/test_paper_probe.py` | probe signal + marker + gating | Create |
| `tests/test_managed_profiles.py` | definitions reproducibility + labels | Create |
| `tests/test_managed_reconcile.py` | reconciler behavior matrix | Create |
| `tests/test_profiles_meta.py` | `get_meta`/`set_meta` | Create |
| `tests/test_supervisor_managed.py` | supervisor reconcile + probe-complete wiring | Create |

---

## Task 1: EMA indicator

**Files:**
- Modify: `src/swingbot/indicators.py`
- Test: `tests/test_indicators.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_indicators.py`:

```python
import pandas as pd

from swingbot.indicators import ema


def test_ema_constant_series_equals_constant():
    s = pd.Series([5.0] * 50)
    result = ema(s, period=10)
    assert abs(result.iloc[-1] - 5.0) < 1e-9


def test_ema_warmup_is_nan_then_defined():
    s = pd.Series(range(1, 31), dtype="float64")
    result = ema(s, period=10)
    assert pd.isna(result.iloc[0])          # before min_periods
    assert not pd.isna(result.iloc[-1])     # defined once warmed up


def test_ema_more_responsive_than_sma_on_a_jump():
    from swingbot.indicators import sma
    s = pd.Series([10.0] * 20 + [20.0] * 5)
    e = ema(s, period=10).iloc[-1]
    m = sma(s, period=10).iloc[-1]
    # EMA weights recent bars more, so it tracks the jump faster than SMA.
    assert e > m
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_indicators.py -k ema -v`
Expected: FAIL with `ImportError: cannot import name 'ema'`.

- [ ] **Step 3: Write minimal implementation**

Add to `src/swingbot/indicators.py` (after `sma`):

```python
def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, min_periods=period, adjust=False).mean()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_indicators.py -k ema -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit and push**

```bash
git add src/swingbot/indicators.py tests/test_indicators.py
git commit -m "feat(indicators): add EMA"
git push origin master
```

---

## Task 2: EMA trend signal + registry

**Files:**
- Create: `src/swingbot/signals/ema_trend.py`
- Modify: `src/swingbot/confluence.py`
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_signals.py`:

```python
import pandas as pd

from swingbot.signals.ema_trend import EmaTrendSignal
from swingbot.types import MarketContext


def _ctx(closes):
    df = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=len(closes), freq="15min", tz="UTC"),
        "open": closes, "high": closes, "low": closes,
        "close": closes, "volume": [1.0] * len(closes),
    })
    return MarketContext(candles=df)


def test_ema_trend_strong_uptrend_scores_high():
    closes = [float(x) for x in range(1, 61)]          # steadily rising
    sig = EmaTrendSignal(weight=1.0, fast=12, slow=26, band=0.01)
    r = sig.evaluate(_ctx(closes))
    assert r.name == "ema_trend"
    assert r.score >= 0.9
    assert r.meta["spread"] > 0


def test_ema_trend_downtrend_scores_zero():
    closes = [float(x) for x in range(60, 0, -1)]       # steadily falling
    sig = EmaTrendSignal(weight=1.0, fast=12, slow=26, band=0.01)
    r = sig.evaluate(_ctx(closes))
    assert r.score == 0.0


def test_ema_trend_warmup_scores_zero():
    closes = [10.0, 11.0, 12.0]                          # too short for slow EMA
    sig = EmaTrendSignal(weight=1.0, fast=12, slow=26, band=0.01)
    r = sig.evaluate(_ctx(closes))
    assert r.score == 0.0
    assert r.meta["ema_fast"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_signals.py -k ema_trend -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.signals.ema_trend'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/swingbot/signals/ema_trend.py`:

```python
from __future__ import annotations

from swingbot.indicators import ema
from swingbot.types import MarketContext, SignalResult


class EmaTrendSignal:
    """Honest trend signal: long bias when the fast EMA leads the slow EMA.

    score = clamp(spread / band, 0, 1), where spread = (ema_fast - ema_slow) / ema_slow.
    A non-positive spread (no uptrend) scores 0; warmup NaNs score 0.
    """

    name = "ema_trend"

    def __init__(self, weight: float, fast: int = 12, slow: int = 26, band: float = 0.01):
        if fast >= slow:
            raise ValueError("fast period must be < slow period")
        self.weight = weight
        self.fast = fast
        self.slow = slow
        self.band = band

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        close = ctx.candles["close"]
        ef = ema(close, self.fast).iloc[-1]
        es = ema(close, self.slow).iloc[-1]
        if ef != ef or es != es or es == 0:  # NaN warmup or undefined
            return SignalResult(self.name, 0.0, {"ema_fast": None, "ema_slow": None, "spread": None})
        spread = (ef - es) / es
        score = max(0.0, min(1.0, spread / self.band))
        return SignalResult(
            self.name, score,
            {"ema_fast": float(ef), "ema_slow": float(es), "spread": float(spread)},
        )
```

Then register it in `src/swingbot/confluence.py`. Add the import next to the other signal imports:

```python
from swingbot.signals.ema_trend import EmaTrendSignal
```

and add to `_REGISTRY`:

```python
    "ema_trend": EmaTrendSignal,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_signals.py -k ema_trend -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit and push**

```bash
git add src/swingbot/signals/ema_trend.py src/swingbot/confluence.py tests/test_signals.py
git commit -m "feat(signals): add honest EMA trend signal and register it"
git push origin master
```

---

## Task 3: Managed profile definitions + labels

**Files:**
- Create: `src/swingbot/managed_profiles.py`
- Test: `tests/test_managed_profiles.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_managed_profiles.py`:

```python
from swingbot.managed_profiles import (
    MANAGED_PROFILE_NAMES,
    MANAGED_LABELS,
    MANAGED_VERSION,
    managed_definitions,
)
from swingbot.profile import StrategyProfile


def test_strategy_definitions_present_and_reproducible():
    a = managed_definitions(enable_probe=False)
    b = managed_definitions(enable_probe=False)
    assert a == b                       # reproducible (same dict every call)
    assert set(a) == {"btc_trend", "eth_trend"}
    assert "paper_probe" not in a


def test_probe_included_only_when_enabled():
    with_probe = managed_definitions(enable_probe=True)
    assert "paper_probe" in with_probe
    assert with_probe["paper_probe"]["signals"] == {"paper_probe": {"weight": 1.0}}


def test_definitions_are_valid_profiles():
    for pdict in managed_definitions(enable_probe=True).values():
        StrategyProfile.from_dict(pdict)        # must not raise


def test_trend_profiles_use_ema_trend_signal():
    defs = managed_definitions(enable_probe=False)
    assert "ema_trend" in defs["btc_trend"]["signals"]
    assert defs["eth_trend"]["symbol"] == "ETH/USD"


def test_probe_allows_all_regimes_so_it_can_fire():
    # The probe must not be blocked by the regime gate; it allows every regime.
    probe = managed_definitions(enable_probe=True)["paper_probe"]
    assert set(probe["allowed_regimes"]) == {"uptrend", "neutral", "downtrend"}


def test_names_and_labels_cover_all_managed():
    assert MANAGED_PROFILE_NAMES == {"btc_trend", "eth_trend", "paper_probe"}
    assert MANAGED_LABELS["paper_probe"]["kind"] == "probe"
    assert MANAGED_LABELS["btc_trend"]["kind"] == "strategy"
    assert isinstance(MANAGED_VERSION, int)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_managed_profiles.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.managed_profiles'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/swingbot/managed_profiles.py`:

```python
from __future__ import annotations

# Bump when the managed definitions below change in a way that should re-seed.
MANAGED_VERSION = 1

# Every name the reconciler is allowed to create/own. Anything NOT in this set
# is a user profile and must never be deleted or overwritten.
MANAGED_PROFILE_NAMES = {"btc_trend", "eth_trend", "paper_probe"}

# UI/labeling metadata so the dashboard can distinguish strategies from the probe.
MANAGED_LABELS = {
    "btc_trend": {"kind": "strategy", "label": "BTC Trend (EMA)"},
    "eth_trend": {"kind": "strategy", "label": "ETH Trend (EMA)"},
    "paper_probe": {"kind": "probe", "label": "proof-of-life probe"},
}


def _trend_profile(symbol: str) -> dict:
    return {
        "symbol": symbol,
        "benchmark_symbol": "BTC/USD",
        "timeframe": "15m",
        "htf_timeframe": "4h",
        "signals": {"ema_trend": {"weight": 1.0, "fast": 12, "slow": 26, "band": 0.01}},
        "entry_threshold": 0.5,
        "regime_ma_period": 50,
        "allowed_regimes": ["uptrend", "neutral"],
        "atr_period": 14,
        "stop_atr_mult": 1.5,
        "take_profit_atr_mult": 2.0,
        "max_hold_bars": 32,
        "risk_per_trade": 0.01,
        "max_position_frac": 0.25,
    }


def _probe_profile() -> dict:
    # Deterministic, market-independent. Allows every regime so the regime gate
    # cannot block a bounded paper entry. Tiny risk; still goes through the full
    # regime/risk/sizing/portfolio/order/fill/persistence pipeline.
    return {
        "symbol": "BTC/USD",
        "benchmark_symbol": "BTC/USD",
        "timeframe": "15m",
        "htf_timeframe": "4h",
        "signals": {"paper_probe": {"weight": 1.0}},
        "entry_threshold": 0.5,
        "regime_ma_period": 50,
        "allowed_regimes": ["uptrend", "neutral", "downtrend"],
        "atr_period": 14,
        "stop_atr_mult": 1.5,
        "take_profit_atr_mult": 2.0,
        "max_hold_bars": 8,
        "risk_per_trade": 0.002,
        "max_position_frac": 0.02,
    }


def managed_definitions(enable_probe: bool) -> dict[str, dict]:
    """Return name -> profile dict for managed profiles. Pure and reproducible.

    The probe is included only when ``enable_probe`` is True (callers also gate on
    ``mode == "paper"`` before passing True).
    """
    defs: dict[str, dict] = {
        "btc_trend": _trend_profile("BTC/USD"),
        "eth_trend": _trend_profile("ETH/USD"),
    }
    if enable_probe:
        defs["paper_probe"] = _probe_profile()
    return defs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_managed_profiles.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit and push**

```bash
git add src/swingbot/managed_profiles.py tests/test_managed_profiles.py
git commit -m "feat(managed): add reproducible managed profile definitions and labels"
git push origin master
```

---

## Task 4: Probe signal, marker store, and fire-once gate

**Files:**
- Create: `src/swingbot/signals/paper_probe.py`
- Create: `src/swingbot/probe_marker.py`
- Modify: `src/swingbot/confluence.py`
- Test: `tests/test_paper_probe.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_paper_probe.py`:

```python
import os

import pandas as pd

from swingbot.probe_marker import ProbeMarkerStore, probe_should_fire
from swingbot.signals.paper_probe import PaperProbeSignal
from swingbot.types import MarketContext


def _ctx():
    df = pd.DataFrame({
        "ts": pd.date_range("2026-01-01", periods=5, freq="15min", tz="UTC"),
        "open": [1.0] * 5, "high": [1.0] * 5, "low": [1.0] * 5,
        "close": [1.0] * 5, "volume": [1.0] * 5,
    })
    return MarketContext(candles=df)


def test_probe_signal_always_fires_deterministically():
    sig = PaperProbeSignal(weight=1.0)
    r = sig.evaluate(_ctx())
    assert r.name == "paper_probe"
    assert r.score == 1.0
    assert r.meta["probe"] is True


def test_marker_persists_completion(tmp_path):
    db = str(tmp_path / "probe.db")
    store = ProbeMarkerStore(db)
    assert store.is_complete("paper_probe") is False
    store.mark_complete("paper_probe")
    assert store.is_complete("paper_probe") is True
    # survives reopen
    assert ProbeMarkerStore(db).is_complete("paper_probe") is True


def test_should_fire_requires_enabled_paper_and_not_complete(tmp_path):
    store = ProbeMarkerStore(str(tmp_path / "probe.db"))
    assert probe_should_fire(store, enabled=True, mode="paper") is True
    assert probe_should_fire(store, enabled=False, mode="paper") is False
    assert probe_should_fire(store, enabled=True, mode="live") is False
    store.mark_complete("paper_probe")
    assert probe_should_fire(store, enabled=True, mode="paper") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_paper_probe.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.probe_marker'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/swingbot/signals/paper_probe.py`:

```python
from __future__ import annotations

from swingbot.types import MarketContext, SignalResult


class PaperProbeSignal:
    """Deterministic proof-of-life signal. Always returns a maximal score so the
    probe profile produces exactly one bounded paper entry through the normal
    pipeline. NOT a trading strategy; gated by env + mode + a durable marker.
    """

    name = "paper_probe"

    def __init__(self, weight: float):
        self.weight = weight

    def evaluate(self, ctx: MarketContext) -> SignalResult:
        return SignalResult(self.name, 1.0, {"probe": True})
```

Create `src/swingbot/probe_marker.py`:

```python
from __future__ import annotations

import sqlite3


class ProbeMarkerStore:
    """Durable 'this probe has already fired' marker (SQLite)."""

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS probe_markers (name TEXT PRIMARY KEY)"
        )
        self._conn.commit()

    def is_complete(self, name: str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM probe_markers WHERE name=?", (name,)
        ).fetchone() is not None

    def mark_complete(self, name: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO probe_markers (name) VALUES (?)", (name,)
        )
        self._conn.commit()


def probe_should_fire(store: ProbeMarkerStore, *, enabled: bool, mode: str,
                      name: str = "paper_probe") -> bool:
    """The probe may run only when explicitly enabled, in paper mode, and not yet
    completed. Any other combination returns False (rejected)."""
    if not enabled or mode != "paper":
        return False
    return not store.is_complete(name)
```

Register the probe signal in `src/swingbot/confluence.py`. Add the import:

```python
from swingbot.signals.paper_probe import PaperProbeSignal
```

and add to `_REGISTRY`:

```python
    "paper_probe": PaperProbeSignal,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_paper_probe.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit and push**

```bash
git add src/swingbot/signals/paper_probe.py src/swingbot/probe_marker.py src/swingbot/confluence.py tests/test_paper_probe.py
git commit -m "feat(probe): add deterministic paper-probe signal, marker store, and fire-once gate"
git push origin master
```

---

## Task 5: Generic meta accessors on ProfileStore

**Files:**
- Modify: `src/swingbot/profiles.py`
- Test: `tests/test_profiles_meta.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_profiles_meta.py`:

```python
from swingbot.profiles import ProfileStore


def test_get_meta_missing_returns_none(tmp_path):
    store = ProfileStore(str(tmp_path / "p.db"))
    assert store.get_meta("managed_version") is None


def test_set_then_get_meta_roundtrips_and_persists(tmp_path):
    db = str(tmp_path / "p.db")
    store = ProfileStore(db)
    store.set_meta("managed_version", "1")
    assert store.get_meta("managed_version") == "1"
    assert ProfileStore(db).get_meta("managed_version") == "1"  # survives reopen


def test_meta_does_not_collide_with_active_pointer(tmp_path):
    store = ProfileStore(str(tmp_path / "p.db"))
    store.save("u", {"symbol": "BTC/USD"})
    store.set_active("u")
    store.set_meta("managed_version", "2")
    assert store.get_active_name() == "u"
    assert store.get_meta("managed_version") == "2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_profiles_meta.py -v`
Expected: FAIL with `AttributeError: 'ProfileStore' object has no attribute 'get_meta'`.

- [ ] **Step 3: Write minimal implementation**

Add these methods to `ProfileStore` in `src/swingbot/profiles.py` (place them right after `get_active`):

```python
    # --- generic meta key/value (managed reconciliation bookkeeping) ---
    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value)
        )
        self._conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_profiles_meta.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit and push**

```bash
git add src/swingbot/profiles.py tests/test_profiles_meta.py
git commit -m "feat(profiles): add generic get_meta/set_meta accessors"
git push origin master
```

---

## Task 6: Versioned managed-profile reconciliation

**Files:**
- Modify: `src/swingbot/managed_profiles.py`
- Test: `tests/test_managed_reconcile.py`

This is the safety-critical task: seed/upgrade managed profiles, **back up the full profile set before any write**, and **never delete or overwrite user profiles**.

- [ ] **Step 1: Write the failing test**

Create `tests/test_managed_reconcile.py`:

```python
import json
import os

from swingbot import managed_profiles as mp
from swingbot.managed_profiles import reconcile_managed_profiles
from swingbot.profiles import ProfileStore


def _store(tmp_path):
    return ProfileStore(str(tmp_path / "p.db"))


def test_fresh_seed_creates_and_arms_trend_profiles(tmp_path):
    store = _store(tmp_path)
    backup_dir = str(tmp_path / "backups")
    report = reconcile_managed_profiles(
        store, enable_probe=False, mode="paper", backup_dir=backup_dir)
    assert set(report.seeded) == {"btc_trend", "eth_trend"}
    assert store.get("btc_trend") is not None
    assert "btc_trend" in store.list_armed()
    assert "paper_probe" not in store.list()


def test_user_profiles_are_never_deleted_or_overwritten(tmp_path):
    store = _store(tmp_path)
    store.save("my_strategy", {"symbol": "SOL/USD", "entry_threshold": 0.42})
    reconcile_managed_profiles(
        store, enable_probe=True, mode="paper", backup_dir=str(tmp_path / "b"))
    assert store.get("my_strategy") == {"symbol": "SOL/USD", "entry_threshold": 0.42}


def test_idempotent_second_run_makes_no_change_and_no_backup(tmp_path):
    store = _store(tmp_path)
    backup_dir = str(tmp_path / "backups")
    reconcile_managed_profiles(store, enable_probe=False, mode="paper", backup_dir=backup_dir)
    second = reconcile_managed_profiles(store, enable_probe=False, mode="paper", backup_dir=backup_dir)
    assert second.seeded == [] and second.upgraded == [] and second.removed == []
    assert second.backup_path is None


def test_version_bump_backs_up_then_upgrades(tmp_path, monkeypatch):
    store = _store(tmp_path)
    backup_dir = str(tmp_path / "backups")
    reconcile_managed_profiles(store, enable_probe=False, mode="paper", backup_dir=backup_dir)

    # Simulate a new managed version whose definitions differ.
    def fake_defs(enable_probe):
        d = mp.managed_definitions(enable_probe)
        d["btc_trend"]["entry_threshold"] = 0.55
        return d
    monkeypatch.setattr(mp, "MANAGED_VERSION", mp.MANAGED_VERSION + 1)
    monkeypatch.setattr(mp, "managed_definitions", fake_defs)

    report = reconcile_managed_profiles(store, enable_probe=False, mode="paper", backup_dir=backup_dir)
    assert "btc_trend" in report.upgraded
    assert report.backup_path is not None and os.path.exists(report.backup_path)
    assert store.get("btc_trend")["entry_threshold"] == 0.55
    backup = json.load(open(report.backup_path))
    assert backup["profiles"]["btc_trend"]["entry_threshold"] == 0.5  # pre-upgrade value


def test_probe_rejected_when_mode_not_paper(tmp_path):
    store = _store(tmp_path)
    reconcile_managed_profiles(store, enable_probe=True, mode="live", backup_dir=str(tmp_path / "b"))
    assert "paper_probe" not in store.list()


def test_disabling_probe_removes_managed_probe_only(tmp_path):
    store = _store(tmp_path)
    backup_dir = str(tmp_path / "backups")
    reconcile_managed_profiles(store, enable_probe=True, mode="paper", backup_dir=backup_dir)
    assert "paper_probe" in store.list()
    report = reconcile_managed_profiles(store, enable_probe=False, mode="paper", backup_dir=backup_dir)
    assert "paper_probe" in report.removed
    assert "paper_probe" not in store.list()
    assert store.get("btc_trend") is not None        # strategies untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_managed_reconcile.py -v`
Expected: FAIL with `ImportError: cannot import name 'reconcile_managed_profiles'`.

- [ ] **Step 3: Write minimal implementation**

Add to the top of `src/swingbot/managed_profiles.py` (imports):

```python
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
```

Append to `src/swingbot/managed_profiles.py`:

```python
@dataclass
class ReconcileReport:
    seeded: list[str] = field(default_factory=list)
    upgraded: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    preserved_user: list[str] = field(default_factory=list)
    backup_path: str | None = None
    version_from: int | None = None
    version_to: int = MANAGED_VERSION


def backup_profiles(store, backup_dir: str, now: datetime | None = None) -> str:
    """Dump the full profile set (and armed flags) to a timestamped JSON file.
    Returns the path written."""
    now = now or datetime.now(timezone.utc)
    os.makedirs(backup_dir, exist_ok=True)
    snapshot = {
        "ts": now.isoformat(),
        "profiles": {name: store.get(name) for name in store.list()},
        "armed": list(store.list_armed()),
    }
    path = os.path.join(backup_dir, f"profiles-{now.strftime('%Y%m%dT%H%M%S%f')}.json")
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)
    return path


def reconcile_managed_profiles(store, *, enable_probe: bool, mode: str,
                               backup_dir: str, now: datetime | None = None) -> ReconcileReport:
    """Seed/upgrade managed profiles to the current MANAGED_VERSION.

    Invariants:
      * Never deletes or overwrites a USER profile (any name not previously
        seeded as managed).
      * Backs up the entire profile set BEFORE making any change.
      * The probe is included only when ``enable_probe`` AND ``mode == 'paper'``.
    """
    # Read the live module attrs so monkeypatched version/defs are honored.
    import swingbot.managed_profiles as _self

    prev_version = store.get_meta("managed_version")
    prev_version_int = int(prev_version) if prev_version is not None else None
    prev_names = set(json.loads(store.get_meta("managed_names") or "[]"))

    target = _self.managed_definitions(enable_probe and mode == "paper")
    target_names = set(target)

    seeded, upgraded = [], []
    for name, pdict in target.items():
        existing = store.get(name)
        if existing is None:
            seeded.append(name)
        elif existing != pdict:
            upgraded.append(name)
    # Managed-origin names we previously created but no longer want (e.g. probe off).
    removed = sorted(prev_names - target_names)

    version_changed = prev_version_int != _self.MANAGED_VERSION
    changed = bool(seeded or upgraded or removed or version_changed)

    report = ReconcileReport(
        seeded=sorted(seeded), upgraded=sorted(upgraded), removed=removed,
        preserved_user=sorted(set(store.list()) - prev_names - target_names),
        version_from=prev_version_int, version_to=_self.MANAGED_VERSION,
    )
    if not changed:
        return report

    # Back up the full set BEFORE any mutation.
    report.backup_path = backup_profiles(store, backup_dir, now)

    for name, pdict in target.items():
        store.save(name, pdict)
        # Arm strategies and the probe so the supervisor runs them.
        store.arm(name)
    for name in removed:
        if store.is_armed(name):
            store.disarm(name)
        store.delete(name)

    store.set_meta("managed_version", str(_self.MANAGED_VERSION))
    store.set_meta("managed_names", json.dumps(sorted(target_names)))
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_managed_reconcile.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit and push**

```bash
git add src/swingbot/managed_profiles.py tests/test_managed_reconcile.py
git commit -m "feat(managed): versioned reconciler with backup and user-profile preservation"
git push origin master
```

---

## Task 7: Supervisor wiring — reconcile at build, mark probe complete

**Files:**
- Modify: `src/swingbot/supervisor.py`
- Modify: `src/swingbot/webmain.py`
- Test: `tests/test_supervisor_managed.py`

The supervisor accepts an optional reconciliation callback and an optional probe-marker store. On `build()` it runs reconciliation (so managed strategies are armed). During `tick_all`, when a managed probe strategy reaches a terminal entry (`ENTERED`/`EXITED`), it records the durable completion marker so the probe fires at most once.

- [ ] **Step 1: Write the failing test**

Create `tests/test_supervisor_managed.py`:

```python
from swingbot.probe_marker import ProbeMarkerStore
from swingbot.supervisor import PortfolioSupervisor
from swingbot.types import DecisionCode, DecisionResult


def _supervisor(tmp_path, **kw):
    db = str(tmp_path / "swingbot.db")
    return PortfolioSupervisor(
        profiles=__import__("swingbot.profiles", fromlist=["ProfileStore"]).ProfileStore(db),
        creds=None, state_db=db, mode="paper", **kw)


def test_build_runs_reconcile_hook(tmp_path):
    calls = []
    sup = _supervisor(tmp_path, reconcile=lambda: calls.append(True))
    # build() with no creds/market won't construct orchestrators, but must run reconcile.
    try:
        sup.build()
    except Exception:
        pass
    assert calls == [True]


def test_note_decision_marks_probe_complete_once(tmp_path):
    marker = ProbeMarkerStore(str(tmp_path / "probe.db"))
    sup = _supervisor(tmp_path, probe_marker=marker)
    assert marker.is_complete("paper_probe") is False
    sup.note_managed_decision("paper_probe", DecisionResult(DecisionCode.ENTERED, "entered"))
    assert marker.is_complete("paper_probe") is True


def test_note_decision_ignores_non_probe_and_non_terminal(tmp_path):
    marker = ProbeMarkerStore(str(tmp_path / "probe.db"))
    sup = _supervisor(tmp_path, probe_marker=marker)
    sup.note_managed_decision("btc_trend", DecisionResult(DecisionCode.ENTERED, "x"))
    sup.note_managed_decision("paper_probe", DecisionResult(DecisionCode.SIGNAL_BELOW_THRESHOLD, "x"))
    assert marker.is_complete("paper_probe") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_supervisor_managed.py -v`
Expected: FAIL — `PortfolioSupervisor.__init__` got an unexpected keyword `reconcile` (and `note_managed_decision` is undefined).

- [ ] **Step 3: Write minimal implementation**

In `src/swingbot/supervisor.py`, extend `PortfolioSupervisor.__init__` to accept and store two optional collaborators. Add these parameters to the signature (after the existing ones, with defaults so all current callers keep working):

```python
                 reconcile=None, probe_marker=None,
```

and in the body store them:

```python
        self._reconcile = reconcile
        self._probe_marker = probe_marker
```

At the very start of `build()` (before it touches creds/profiles), run the reconcile hook if present:

```python
        if self._reconcile is not None:
            self._reconcile()
```

Add a new method (near `tick_all`):

```python
    def note_managed_decision(self, name: str, decision) -> None:
        """Record the durable proof-of-life marker after the probe makes its one
        bounded entry. No-op for non-probe strategies, non-terminal decisions, or
        when no marker store is configured."""
        from swingbot.types import DecisionCode
        if self._probe_marker is None or name != "paper_probe":
            return
        if decision.code in (DecisionCode.ENTERED, DecisionCode.EXITED):
            self._probe_marker.mark_complete("paper_probe")
```

Then, inside `tick_all`, where each armed strategy's `Orchestrator.tick()` result is obtained, call the hook. Find the loop in `tick_all` that iterates strategies and produces a `DecisionResult` per strategy (variable holding the per-strategy name and its decision), and add immediately after the decision is computed:

```python
            self.note_managed_decision(name, decision)
```

> Note for the implementer: match the existing variable names in `tick_all`. If the loop variable for the strategy name differs (e.g. `strat`/`profile.symbol`), use that. The call must run once per strategy per tick with that strategy's `DecisionResult`.

Now wire it in `src/swingbot/webmain.py`. After `profiles`, `runtime_state`, and `DATA_DIR` are set up and before constructing the supervisor, add:

```python
    from swingbot.managed_profiles import reconcile_managed_profiles
    from swingbot.probe_marker import ProbeMarkerStore

    probe_marker = ProbeMarkerStore(os.path.join(DATA_DIR, "probe_markers.db"))
    enable_probe = os.environ.get("SWINGBOT_ENABLE_PAPER_PROBE") == "1"
    backup_dir = os.path.join(DATA_DIR, "backups")

    def _reconcile_managed():
        reconcile_managed_profiles(
            profiles, enable_probe=enable_probe, mode="paper", backup_dir=backup_dir)
```

Then pass the two new collaborators when constructing the supervisor (add to the existing `PortfolioSupervisor(...)` call):

```python
        reconcile=_reconcile_managed, probe_marker=probe_marker,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_supervisor_managed.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit and push**

```bash
git add src/swingbot/supervisor.py src/swingbot/webmain.py tests/test_supervisor_managed.py
git commit -m "feat(supervisor): reconcile managed profiles on build; mark probe complete on entry"
git push origin master
```

---

## Task 8: Full regression gate + frontend build

**Files:** none (verification only).

- [ ] **Step 1: Run the full Python suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all green. Baseline before Phase 4 was **521 passed, 6 skipped**; this phase adds ~30 tests, so expect roughly **550+ passed, 6 skipped** with **0 failures**. If anything fails, fix it before continuing (do not edit unrelated tests to force green).

- [ ] **Step 2: Run ruff**

Run: `.venv/bin/python -m ruff check src/`
Expected: `All checks passed!`

- [ ] **Step 3: Build the frontend (must stay green; Phase 4 does not touch it)**

Run: `cd frontend && npm run build`
Expected: build succeeds with no errors.

- [ ] **Step 4: Final confirmation commit (if anything was adjusted) and push**

If Steps 1–3 required any fix:

```bash
git add <only the files you changed>
git commit -m "fix: Phase 4 regression cleanup"
git push origin master
```

If nothing needed changing, there is nothing to commit — just confirm the suite, ruff, and build are green and that every prior task was pushed (`git status` shows `Your branch is up to date with 'origin/master'`).

---

## Self-Review (run before declaring the plan done)

**Spec coverage (§5 Phase 4):**
1. "Add EMA with tests" → Task 1. ✓
2. "Add honest trend strategy signal/profile definitions" → Tasks 2 (signal) + 3 (profiles). ✓
3. "Versioned managed-profile reconciliation without deleting user profiles" → Task 6 (backup + preservation + version). ✓
4. "Add opt-in paper probe, or formally remove bounded-entry acceptance" → opt-in probe chosen; Tasks 3 (def), 4 (signal/marker/gate), 7 (wiring). ✓
5. "Disable conflicting profile mutation paths only if managed-canvas is enforced server-side" → **deferred / out of scope** (managed-canvas mode is not being adopted now). Recorded as a decision below; the reconciler's user-profile preservation gives the real safety guarantee. ✓
- Exit criterion: definitions reproducible (Task 3 test), existing data backed up/preserved (Task 6 tests), proof separated from strategy (probe is a distinct signal/profile labeled `kind: "probe"`, env+mode+marker gated). ✓

**Test matrix (§6) coverage added here:** Managed canvas → fresh seed, user profiles preserved, version upgrade, (mutation enforcement intentionally deferred). Probe gating (enabled/paper/complete). EMA freshness via closed-bar last row.

**Decisions locked (do not re-open during execution):**
- Item #4: **opt-in `paper_probe`** kept strictly separate from strategies (preserves success criterion #10). Disabled by default; enable with `SWINGBOT_ENABLE_PAPER_PROBE=1`.
- Item #5: **managed-canvas server-side mutation enforcement is out of scope** for Phase 4 (spec makes it conditional on a mode we are not adopting). User-profile preservation in the reconciler is the safety guarantee instead.

**Placeholder scan:** no TBD/TODO; every code step has complete code. **Type consistency:** `paper_probe` name, `MANAGED_PROFILE_NAMES`, `managed_definitions(enable_probe)`, `reconcile_managed_profiles(...)`, `ProbeMarkerStore.is_complete/mark_complete`, `probe_should_fire(store, enabled, mode)`, `note_managed_decision(name, decision)` are used identically across tasks.
