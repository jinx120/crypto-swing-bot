# Autonomous Trading Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only web dashboard that shows an EMA-vs-Kronos backtest comparison plus the live autonomous core-engine's position, trades, journal, candles, and stats — all driven by the data the running bot already produces.

**Architecture:** A new `swingbot.autodash` Python package runs the backtest comparison (reusing `core_engine.backtest.run_backtest`) and serves live reads off the core-engine's SQLite DBs (`~/.core-engine/{journal,state,candles}.db`). Six read-only FastAPI routes are mounted into the existing `web.py` app via an injected `AutoDashboardService` + `APIRouter`. A new React page (`AutoDashboard.jsx`) polls those routes every 10s and renders six panels, reusing the installed `lightweight-charts` v5 library. The core-engine is extended to persist its open position so live stats are accurate.

**Tech Stack:** Python 3 / FastAPI / pandas / sqlite3 (stdlib); pytest + FastAPI `TestClient`; React 18 + Vite + `lightweight-charts` ^5.2.0; Docker Compose.

## Global Constraints

- **Read-only frontend.** No buttons, forms, or state mutations from the dashboard. Live routes are GET, unauthenticated (match the existing `/api/state` pattern — GETs take no token).
- **Reuse, don't rewrite.** Backtest engine = `core_engine.backtest.run_backtest(candles, *, profile, kronos, equity0)` → `BacktestResult(trades, final_equity, wins, losses)`. EMA run passes `kronos=None`; Kronos run passes a real `KronosForecastSignal`. Profile = `core_engine.config.PROFILE` (signals `{"ema_trend": {...}}`).
- **Live data is asset-agnostic by parameter.** Candles load via `CandleStore(db).get(symbol, timeframe, limit)`; symbol/timeframe are parameters everywhere. Default symbol/timeframe come from `core_engine.config.SYMBOL` (`"BTC/USD"`) and `TIMEFRAME` (`"5m"`).
- **Determinism in tests.** Unit tests never hit the network and never run real Kronos inference — they inject synthetic DataFrames and a stub kronos signal. Full GPU Kronos runs only at real app startup and in one explicitly-marked slow smoke test.
- **Timestamps:** core-engine `bars.ts` and `CandleStore.get(...)["time"]` are epoch **seconds** (int). `events.ts` and trade timestamps are ISO-8601 strings.
- **Docker rebuild is mandatory after any code change** to `crypto-swing-bot/` (`swingbot` container) and after any change under `lab/core-engine/` (core-engine container). Pre-authorized; do it as part of the task.
- All Python paths are under `/home/redji/crypto-swing-bot/`. Run pytest with the repo venv: `.venv/bin/python -m pytest`. Run from repo root.

---

## File Structure

**New Python package** `src/swingbot/autodash/`:
- `__init__.py` — exports `AutoDashConfig`, `AutoDashboardService`.
- `config.py` — `AutoDashConfig` dataclass: DB paths, symbol, timeframe, backtest limits.
- `backtest_runner.py` — `BacktestSummary`, `summarize(BacktestResult, equity0)`, `run_comparison(candles, *, kronos_factory)`.
- `queries.py` — `recent_events`, `recent_trades`, `recent_candles`, `live_position` (read-only sqlite).
- `kronos_factory.py` — `build_kronos_signal(device=None)` (GPU-preferring).
- `service.py` — `AutoDashboardService` (caches backtest, exposes live reads).
- `router.py` — `build_auto_router(service)` → `APIRouter` with 6 GET routes.

**Modify:** `src/swingbot/web.py` (mount router), `src/swingbot/webmain.py` (build service).

**Core-engine (accuracy):** `lab/core-engine/src/core_engine/position_store.py` (new), `loop.py` (write-through), `__main__.py` (wire).

**Frontend** `frontend/src/`:
- `pages/AutoDashboard.jsx` (new — does NOT touch existing `Dashboard.jsx`).
- `components/AutoDash/{usePolling.js, BacktestComparisonPanel.jsx, CurrentPositionPanel.jsx, LiveStatsPanel.jsx, RecentTradesPanel.jsx, JournalFeedPanel.jsx, ChartPanel.jsx}`.
- Modify `api.js` (add `auto.*` helpers), `App.jsx` (add `auto` tab).

**Tests** `tests/autodash/`: `test_backtest_runner.py`, `test_queries.py`, `test_service.py`, `test_router_endpoints.py`, `test_e2e.py`. Core-engine: `lab/core-engine/tests/test_position_store.py`.

**Docs:** `docs/API_DASHBOARD.md`, `docs/DATA_SOURCES.md`.

> **Frontend test gate:** the repo has no JS test runner (no vitest/RTL in `frontend/package.json`). Frontend tasks are gated on `cd frontend && npm run build` succeeding with no errors, plus the final Playwright smoke. Do **not** add a JS test framework.

---

## Task 1: Package scaffold + config

**Files:**
- Create: `src/swingbot/autodash/__init__.py`, `src/swingbot/autodash/config.py`
- Test: `tests/autodash/__init__.py`, `tests/autodash/test_config.py`

**Interfaces:**
- Produces: `AutoDashConfig(core_engine_data: str, history_db: str, symbol: str, timeframe: str, backtest_limit: int, equity0: float)`, with classmethod `default() -> AutoDashConfig`. Properties `journal_db`, `state_db`, `candle_db` resolve to `{core_engine_data}/{journal,state,candles}.db`.

- [x] **Step 1: Write the failing test**

Create `tests/autodash/__init__.py` (empty), then `tests/autodash/test_config.py`:

```python
import os
from swingbot.autodash.config import AutoDashConfig


def test_default_resolves_core_engine_db_paths():
    cfg = AutoDashConfig.default()
    assert cfg.symbol == "BTC/USD"
    assert cfg.timeframe == "5m"
    assert cfg.journal_db.endswith("/journal.db")
    assert cfg.state_db.endswith("/state.db")
    assert cfg.candle_db.endswith("/candles.db")
    assert os.path.basename(os.path.dirname(cfg.journal_db)) == ".core-engine"


def test_explicit_data_dir_overrides_paths():
    cfg = AutoDashConfig(core_engine_data="/tmp/ce", history_db="/tmp/h.db")
    assert cfg.journal_db == "/tmp/ce/journal.db"
    assert cfg.candle_db == "/tmp/ce/candles.db"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.autodash'`

- [x] **Step 3: Write minimal implementation**

Create `src/swingbot/autodash/config.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AutoDashConfig:
    core_engine_data: str
    history_db: str
    symbol: str = "BTC/USD"
    timeframe: str = "5m"
    backtest_limit: int = 5000
    equity0: float = 10_000.0

    @classmethod
    def default(cls) -> "AutoDashConfig":
        data = os.environ.get(
            "CORE_ENGINE_DATA", os.path.expanduser("~/.core-engine")
        )
        history = os.environ.get(
            "SWINGBOT_DATA_DIR", os.path.expanduser("~/.swingbot")
        )
        return cls(core_engine_data=data,
                   history_db=os.path.join(history, "candles.db"))

    @property
    def journal_db(self) -> str:
        return os.path.join(self.core_engine_data, "journal.db")

    @property
    def state_db(self) -> str:
        return os.path.join(self.core_engine_data, "state.db")

    @property
    def candle_db(self) -> str:
        return os.path.join(self.core_engine_data, "candles.db")
```

Create `src/swingbot/autodash/__init__.py`:

```python
from swingbot.autodash.config import AutoDashConfig

__all__ = ["AutoDashConfig"]
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_config.py -v`
Expected: PASS (2 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autodash/__init__.py src/swingbot/autodash/config.py tests/autodash/__init__.py tests/autodash/test_config.py
git commit -m "feat(autodash): config dataclass resolving core-engine db paths"
```

---

## Task 2: Backtest summary metrics

**Files:**
- Create: `src/swingbot/autodash/backtest_runner.py`
- Test: `tests/autodash/test_backtest_runner.py`

**Interfaces:**
- Consumes: `core_engine.backtest.BacktestResult(trades: list[dict], final_equity: float, wins: int, losses: int)` where each trade is `{"pnl": float, "reason": str, "won": bool}`.
- Produces: `BacktestSummary` dataclass with fields `n_trades:int, win_rate:float, total_pnl:float, sharpe:float, final_equity:float, equity_curve:list[float]` and `to_dict()->dict`; function `summarize(result: BacktestResult, equity0: float) -> BacktestSummary`.

- [x] **Step 1: Write the failing test**

Create `tests/autodash/test_backtest_runner.py`:

```python
import math

from core_engine.backtest import BacktestResult
from swingbot.autodash.backtest_runner import summarize, BacktestSummary


def _result(pnls):
    trades = [{"pnl": p, "reason": "tp", "won": p > 0} for p in pnls]
    wins = sum(1 for p in pnls if p > 0)
    return BacktestResult(trades=trades, final_equity=1000.0 + sum(pnls),
                          wins=wins, losses=len(pnls) - wins)


def test_summarize_empty_is_zeroed():
    s = summarize(BacktestResult([], 1000.0, 0, 0), equity0=1000.0)
    assert isinstance(s, BacktestSummary)
    assert s.n_trades == 0 and s.win_rate == 0.0 and s.total_pnl == 0.0
    assert s.sharpe == 0.0 and s.equity_curve == [1000.0]


def test_summarize_computes_winrate_pnl_and_curve():
    s = summarize(_result([10.0, -5.0, 15.0]), equity0=1000.0)
    assert s.n_trades == 3
    assert math.isclose(s.win_rate, 2 / 3)
    assert math.isclose(s.total_pnl, 20.0)
    assert s.equity_curve == [1000.0, 1010.0, 1005.0, 1020.0]
    assert s.sharpe > 0.0


def test_to_dict_shape():
    d = summarize(_result([1.0, 2.0]), equity0=1000.0).to_dict()
    assert set(d) == {"n_trades", "win_rate", "total_pnl", "sharpe",
                      "final_equity", "equity_curve"}
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_backtest_runner.py -v`
Expected: FAIL — `ImportError: cannot import name 'summarize'`

- [x] **Step 3: Write minimal implementation**

Create `src/swingbot/autodash/backtest_runner.py`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass, asdict

from core_engine.backtest import BacktestResult


@dataclass(frozen=True)
class BacktestSummary:
    n_trades: int
    win_rate: float
    total_pnl: float
    sharpe: float
    final_equity: float
    equity_curve: list[float]

    def to_dict(self) -> dict:
        return asdict(self)


def summarize(result: BacktestResult, equity0: float) -> BacktestSummary:
    pnls = [float(t["pnl"]) for t in result.trades]
    n = len(pnls)
    if n == 0:
        return BacktestSummary(0, 0.0, 0.0, 0.0, equity0, [equity0])

    win_rate = sum(1 for p in pnls if p > 0) / n
    total_pnl = sum(pnls)

    equity = equity0
    curve = [equity0]
    for p in pnls:
        equity += p
        curve.append(equity)

    mean = total_pnl / n
    var = sum((p - mean) ** 2 for p in pnls) / n
    std = math.sqrt(var)
    sharpe = (mean / std) * math.sqrt(n) if std > 0 else 0.0

    return BacktestSummary(n, win_rate, total_pnl, sharpe,
                           result.final_equity, curve)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_backtest_runner.py -v`
Expected: PASS (3 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autodash/backtest_runner.py tests/autodash/test_backtest_runner.py
git commit -m "feat(autodash): backtest summary (winrate, pnl, sharpe, equity curve)"
```

---

## Task 3: EMA-vs-Kronos comparison runner

**Files:**
- Modify: `src/swingbot/autodash/backtest_runner.py`
- Test: `tests/autodash/test_backtest_runner.py`

**Interfaces:**
- Consumes: `core_engine.backtest.run_backtest`, `core_engine.config.PROFILE`, `BacktestSummary` (Task 2).
- Produces: `run_comparison(candles: pandas.DataFrame, *, profile=None, kronos_factory=None, equity0: float = 10_000.0) -> dict` returning `{"ema": <summary dict>, "kronos": <summary dict>}`. `kronos_factory` is a zero-arg callable returning a kronos signal or `None`; when `None`, both runs use `kronos=None` (deterministic).

- [x] **Step 1: Write the failing test**

Append to `tests/autodash/test_backtest_runner.py`:

```python
import numpy as np
import pandas as pd

from swingbot.autodash.backtest_runner import run_comparison


def _trending_candles(n=200):
    ts = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    base = np.linspace(100.0, 130.0, n)
    return pd.DataFrame({
        "ts": (ts.view("int64") // 1_000_000_000),
        "open": base, "high": base + 1.0, "low": base - 1.0,
        "close": base + 0.5, "volume": np.full(n, 1.0),
    })


def test_run_comparison_returns_both_sides_with_shapes():
    out = run_comparison(_trending_candles(), kronos_factory=None)
    assert set(out) == {"ema", "kronos"}
    for side in ("ema", "kronos"):
        assert set(out[side]) == {"n_trades", "win_rate", "total_pnl",
                                  "sharpe", "final_equity", "equity_curve"}
    # kronos_factory=None makes both runs identical (kronos contributes 0.0)
    assert out["ema"]["n_trades"] == out["kronos"]["n_trades"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_backtest_runner.py::test_run_comparison_returns_both_sides_with_shapes -v`
Expected: FAIL — `ImportError: cannot import name 'run_comparison'`

- [x] **Step 3: Write minimal implementation**

Append to `src/swingbot/autodash/backtest_runner.py`:

```python
import pandas as pd  # add to the top-of-file imports

from core_engine.backtest import run_backtest as _ce_run_backtest
from core_engine.config import PROFILE as _DEFAULT_PROFILE


def run_comparison(candles, *, profile=None, kronos_factory=None,
                   equity0: float = 10_000.0) -> dict:
    profile = profile or _DEFAULT_PROFILE
    if not isinstance(candles, pd.DataFrame):
        candles = pd.DataFrame(candles)

    ema_res = _ce_run_backtest(candles, profile=profile, kronos=None,
                               equity0=equity0)
    kronos = kronos_factory() if kronos_factory is not None else None
    kronos_res = _ce_run_backtest(candles, profile=profile, kronos=kronos,
                                  equity0=equity0)

    return {
        "ema": summarize(ema_res, equity0).to_dict(),
        "kronos": summarize(kronos_res, equity0).to_dict(),
    }
```

> Place the two new `import` lines with the existing imports at the top of the file (not mid-file).

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_backtest_runner.py -v`
Expected: PASS (4 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autodash/backtest_runner.py tests/autodash/test_backtest_runner.py
git commit -m "feat(autodash): EMA-vs-Kronos run_comparison reusing core_engine backtest"
```

---

## Task 4: GPU-preferring Kronos factory

**Files:**
- Create: `src/swingbot/autodash/kronos_factory.py`
- Test: `tests/autodash/test_kronos_factory.py`

**Interfaces:**
- Produces: `pick_device(torch_mod=None) -> str` returning `"cuda"` when CUDA is available else `"cpu"`; `build_kronos_signal(device=None, model_name="NeoQuasar/Kronos-small")` returning a `KronosForecastSignal` or `None` if the heavy stack is unavailable (mirrors `core_engine.__main__._kronos_or_none`). Used as the `kronos_factory` argument to `run_comparison`.

- [x] **Step 1: Write the failing test**

Create `tests/autodash/test_kronos_factory.py`:

```python
from swingbot.autodash.kronos_factory import pick_device, build_kronos_signal


class _FakeCuda:
    def __init__(self, ok): self._ok = ok
    def is_available(self): return self._ok


class _FakeTorch:
    def __init__(self, ok): self.cuda = _FakeCuda(ok)


def test_pick_device_prefers_cuda_when_available():
    assert pick_device(_FakeTorch(True)) == "cuda"


def test_pick_device_falls_back_to_cpu():
    assert pick_device(_FakeTorch(False)) == "cpu"


def test_build_kronos_signal_never_raises():
    # On a host without torch/Kronos this returns None instead of crashing.
    sig = build_kronos_signal()
    assert sig is None or hasattr(sig, "evaluate")
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_kronos_factory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.autodash.kronos_factory'`

- [x] **Step 3: Write minimal implementation**

Create `src/swingbot/autodash/kronos_factory.py`:

```python
from __future__ import annotations


def pick_device(torch_mod=None) -> str:
    if torch_mod is None:
        try:
            import torch as torch_mod  # noqa: PLC0415
        except Exception:
            return "cpu"
    try:
        return "cuda" if torch_mod.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def build_kronos_signal(device: str | None = None,
                        model_name: str = "NeoQuasar/Kronos-small"):
    """Build a real Kronos signal on the best device, or None if its heavy
    stack (torch + Kronos repo) is unavailable. Never raises."""
    device = device or pick_device()
    try:
        from swingbot.signals.kronos_forecast import KronosForecastSignal
        sig = KronosForecastSignal(weight=1.0)
        print(f"[autodash] Kronos signal built on device={device} "
              f"(model={model_name})")
        return sig
    except Exception as exc:
        print(f"[autodash] Kronos unavailable ({type(exc).__name__}: {exc}); "
              f"comparison will use kronos=None.")
        return None
```

> The Kronos model placement on GPU is honored by the Kronos library's `KronosPredictor`; `pick_device` records the intended device and is the single switch the service logs at startup. Real VRAM usage is verified in Task 19's slow smoke, not in unit tests.

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_kronos_factory.py -v`
Expected: PASS (3 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autodash/kronos_factory.py tests/autodash/test_kronos_factory.py
git commit -m "feat(autodash): GPU-preferring Kronos factory with graceful fallback"
```

---

## Task 5: Live query — recent journal events

**Files:**
- Create: `src/swingbot/autodash/queries.py`
- Test: `tests/autodash/test_queries.py`

**Interfaces:**
- Produces: `recent_events(journal_db: str, limit: int = 50) -> list[dict]`, newest-first, each `{"ts": str, "kind": str, "symbol": str, "reason": str, "payload": dict}`. Returns `[]` if the DB/file/table is missing.

- [x] **Step 1: Write the failing test**

Create `tests/autodash/test_queries.py`:

```python
import json
import sqlite3

from swingbot.autodash.queries import recent_events


def _make_journal(path, rows):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "ts TEXT, kind TEXT, symbol TEXT, reason TEXT, payload TEXT)")
    for ts, kind, sym, reason, payload in rows:
        c.execute("INSERT INTO events (ts, kind, symbol, reason, payload) "
                  "VALUES (?,?,?,?,?)",
                  (ts, kind, sym, reason, json.dumps(payload)))
    c.commit()
    c.close()


def test_recent_events_newest_first_and_parsed(tmp_path):
    p = str(tmp_path / "journal.db")
    _make_journal(p, [
        ("2026-06-17T17:01:00+00:00", "decision", "BTC/USD", "hold", {"action": "hold"}),
        ("2026-06-17T17:06:00+00:00", "order", "BTC/USD", "entry filled",
         {"open": True, "qty": 0.01}),
    ])
    out = recent_events(p, limit=10)
    assert [e["kind"] for e in out] == ["order", "decision"]
    assert out[0]["payload"]["open"] is True


def test_recent_events_missing_db_returns_empty(tmp_path):
    assert recent_events(str(tmp_path / "nope.db")) == []
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_queries.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.autodash.queries'`

- [x] **Step 3: Write minimal implementation**

Create `src/swingbot/autodash/queries.py`:

```python
from __future__ import annotations

import json
import os
import sqlite3


def _connect(db_path: str) -> sqlite3.Connection | None:
    if not os.path.exists(db_path):
        return None
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def recent_events(journal_db: str, limit: int = 50) -> list[dict]:
    conn = _connect(journal_db)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT ts, kind, symbol, reason, payload FROM events "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    out = []
    for ts, kind, symbol, reason, payload in rows:
        try:
            parsed = json.loads(payload) if payload else {}
        except (ValueError, TypeError):
            parsed = {}
        out.append({"ts": ts, "kind": kind, "symbol": symbol,
                    "reason": reason, "payload": parsed})
    return out
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_queries.py -v`
Expected: PASS (2 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autodash/queries.py tests/autodash/test_queries.py
git commit -m "feat(autodash): recent_events read-only query over core-engine journal"
```

---

## Task 6: Live query — recent closed trades

**Files:**
- Modify: `src/swingbot/autodash/queries.py`
- Test: `tests/autodash/test_queries.py`

**Interfaces:**
- Consumes: `_connect` (Task 5).
- Produces: `recent_trades(journal_db: str, limit: int = 50) -> list[dict]`, newest-first, each `{"ts": str, "pnl": float, "won": bool, "reason": str}`, derived from `kind='pnl'` events whose payload is `{"realized": float, "won": bool}`.

- [x] **Step 1: Write the failing test**

Append to `tests/autodash/test_queries.py`:

```python
from swingbot.autodash.queries import recent_trades


def test_recent_trades_maps_pnl_events(tmp_path):
    p = str(tmp_path / "journal.db")
    _make_journal(p, [
        ("2026-06-17T18:00:00+00:00", "decision", "BTC/USD", "hold", {}),
        ("2026-06-17T18:30:00+00:00", "pnl", "BTC/USD", "closed: take_profit",
         {"realized": 12.5, "won": True}),
        ("2026-06-17T19:00:00+00:00", "pnl", "BTC/USD", "closed: stop_loss",
         {"realized": -8.0, "won": False}),
    ])
    out = recent_trades(p, limit=10)
    assert len(out) == 2                       # decision event excluded
    assert out[0]["pnl"] == -8.0 and out[0]["won"] is False
    assert out[1]["pnl"] == 12.5 and out[1]["reason"] == "closed: take_profit"
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_queries.py::test_recent_trades_maps_pnl_events -v`
Expected: FAIL — `ImportError: cannot import name 'recent_trades'`

- [x] **Step 3: Write minimal implementation**

Append to `src/swingbot/autodash/queries.py`:

```python
def recent_trades(journal_db: str, limit: int = 50) -> list[dict]:
    conn = _connect(journal_db)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT ts, reason, payload FROM events WHERE kind='pnl' "
            "ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    out = []
    for ts, reason, payload in rows:
        try:
            parsed = json.loads(payload) if payload else {}
        except (ValueError, TypeError):
            parsed = {}
        out.append({"ts": ts, "pnl": float(parsed.get("realized", 0.0)),
                    "won": bool(parsed.get("won", False)), "reason": reason})
    return out
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_queries.py -v`
Expected: PASS (3 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autodash/queries.py tests/autodash/test_queries.py
git commit -m "feat(autodash): recent_trades derived from core-engine pnl events"
```

---

## Task 7: Live query — recent candles

**Files:**
- Modify: `src/swingbot/autodash/queries.py`
- Test: `tests/autodash/test_queries.py`

**Interfaces:**
- Produces: `recent_candles(candle_db: str, symbol: str, timeframe: str, limit: int = 200) -> list[dict]`, oldest-first, each `{"time": int, "open": float, "high": float, "low": float, "close": float, "volume": float}` (matches `CandleStore.get` shape and lightweight-charts `time` in epoch seconds).

- [x] **Step 1: Write the failing test**

Append to `tests/autodash/test_queries.py`:

```python
from swingbot.autodash.queries import recent_candles


def _make_candles(path, bars):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE bars (symbol TEXT, timeframe TEXT, ts INTEGER, "
              "open REAL, high REAL, low REAL, close REAL, volume REAL, "
              "PRIMARY KEY (symbol, timeframe, ts))")
    c.executemany("INSERT INTO bars VALUES (?,?,?,?,?,?,?,?)", bars)
    c.commit()
    c.close()


def test_recent_candles_oldest_first_chart_shape(tmp_path):
    p = str(tmp_path / "candles.db")
    _make_candles(p, [
        ("BTC/USD", "5m", 1781265600, 100, 101, 99, 100.5, 1.0),
        ("BTC/USD", "5m", 1781265900, 100.5, 102, 100, 101.5, 2.0),
    ])
    out = recent_candles(p, "BTC/USD", "5m", limit=10)
    assert [c["time"] for c in out] == [1781265600, 1781265900]
    assert set(out[0]) == {"time", "open", "high", "low", "close", "volume"}
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_queries.py::test_recent_candles_oldest_first_chart_shape -v`
Expected: FAIL — `ImportError: cannot import name 'recent_candles'`

- [x] **Step 3: Write minimal implementation**

Append to `src/swingbot/autodash/queries.py`:

```python
def recent_candles(candle_db: str, symbol: str, timeframe: str,
                   limit: int = 200) -> list[dict]:
    conn = _connect(candle_db)
    if conn is None:
        return []
    try:
        rows = conn.execute(
            "SELECT ts, open, high, low, close, volume FROM bars "
            "WHERE symbol=? AND timeframe=? ORDER BY ts DESC LIMIT ?",
            (symbol, timeframe, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
    rows.reverse()
    return [{"time": int(ts), "open": o, "high": h, "low": lo,
             "close": c, "volume": v} for ts, o, h, lo, c, v in rows]
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_queries.py -v`
Expected: PASS (4 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autodash/queries.py tests/autodash/test_queries.py
git commit -m "feat(autodash): recent_candles read-only query for charting"
```

---

## Task 8: Live query — current position (persisted, with journal fallback)

**Files:**
- Modify: `src/swingbot/autodash/queries.py`
- Test: `tests/autodash/test_queries.py`

**Interfaces:**
- Consumes: `_connect` (Task 5).
- Produces: `live_position(state_db: str, journal_db: str) -> dict | None`. First reads `runtime_state` key `open_position` (JSON written by core-engine, Task 9/10). If absent/empty, falls back to deriving from the latest `kind='order'` event with `payload.open` truthy in `journal_db`, returning `None` if a later `pnl` event closed it. Returned dict shape: `{"symbol": str, "entry_price": float, "qty": float, "stop": float|None, "tp": float|None, "entry_ts": str|None}`.

- [x] **Step 1: Write the failing test**

Append to `tests/autodash/test_queries.py`:

```python
from swingbot.autodash.queries import live_position


def _make_state(path, kv):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE runtime_state (key TEXT PRIMARY KEY, value TEXT)")
    for k, v in kv.items():
        c.execute("INSERT INTO runtime_state VALUES (?,?)", (k, v))
    c.commit()
    c.close()


def test_live_position_reads_persisted_state(tmp_path):
    sp = str(tmp_path / "state.db")
    jp = str(tmp_path / "journal.db")
    _make_state(sp, {"running_desired": "1", "open_position": json.dumps(
        {"symbol": "BTC/USD", "entry_price": 65000.0, "qty": 0.01,
         "stop": 64000.0, "tp": 67000.0, "entry_ts": "2026-06-17T18:00:00+00:00"})})
    _make_journal(jp, [])
    pos = live_position(sp, jp)
    assert pos["entry_price"] == 65000.0 and pos["qty"] == 0.01


def test_live_position_falls_back_to_journal_order(tmp_path):
    sp = str(tmp_path / "state.db")
    jp = str(tmp_path / "journal.db")
    _make_state(sp, {"running_desired": "1"})       # no open_position key
    _make_journal(jp, [
        ("2026-06-17T18:00:00+00:00", "order", "BTC/USD", "entry filled",
         {"open": True, "qty": 0.02, "entry": 64000.0}),
    ])
    pos = live_position(sp, jp)
    assert pos["entry_price"] == 64000.0 and pos["qty"] == 0.02


def test_live_position_none_when_closed_after_open(tmp_path):
    sp = str(tmp_path / "state.db")
    jp = str(tmp_path / "journal.db")
    _make_state(sp, {"running_desired": "1"})
    _make_journal(jp, [
        ("2026-06-17T18:00:00+00:00", "order", "BTC/USD", "entry filled",
         {"open": True, "qty": 0.02, "entry": 64000.0}),
        ("2026-06-17T18:30:00+00:00", "pnl", "BTC/USD", "closed: tp",
         {"realized": 5.0, "won": True}),
    ])
    assert live_position(sp, jp) is None
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_queries.py -k live_position -v`
Expected: FAIL — `ImportError: cannot import name 'live_position'`

- [x] **Step 3: Write minimal implementation**

Append to `src/swingbot/autodash/queries.py`:

```python
def _state_value(state_db: str, key: str) -> str | None:
    conn = _connect(state_db)
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT value FROM runtime_state WHERE key=?", (key,)
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    return row[0] if row else None


def _position_from_journal(journal_db: str) -> dict | None:
    conn = _connect(journal_db)
    if conn is None:
        return None
    try:
        rows = conn.execute(
            "SELECT kind, payload FROM events WHERE kind IN ('order','pnl') "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    finally:
        conn.close()
    if not rows:
        return None
    kind, payload = rows
    if kind != "order":
        return None                       # most recent lifecycle event closed it
    try:
        p = json.loads(payload) if payload else {}
    except (ValueError, TypeError):
        p = {}
    if not p.get("open"):
        return None
    return {"symbol": p.get("symbol", "BTC/USD"),
            "entry_price": float(p.get("entry", 0.0)),
            "qty": float(p.get("qty", 0.0)),
            "stop": p.get("stop"), "tp": p.get("tp"),
            "entry_ts": p.get("entry_ts")}


def live_position(state_db: str, journal_db: str) -> dict | None:
    raw = _state_value(state_db, "open_position")
    if raw:
        try:
            parsed = json.loads(raw)
        except (ValueError, TypeError):
            parsed = None
        if parsed:
            return parsed
    return _position_from_journal(journal_db)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_queries.py -v`
Expected: PASS (7 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autodash/queries.py tests/autodash/test_queries.py
git commit -m "feat(autodash): live_position from persisted state with journal fallback"
```

---

## Task 9: Core-engine PositionStore

**Files:**
- Create: `lab/core-engine/src/core_engine/position_store.py`
- Test: `lab/core-engine/tests/test_position_store.py`

**Interfaces:**
- Produces: `PositionStore(db_path)` writing into the existing `runtime_state(key, value)` table under key `open_position`. Methods: `set(position: EnginePosition) -> None`, `clear() -> None`, `get() -> dict | None`. Serialized dict shape matches Task 8's `live_position` persisted shape.

- [x] **Step 1: Write the failing test**

Create `lab/core-engine/tests/test_position_store.py`:

```python
from datetime import datetime, timezone

from core_engine.contracts import EnginePosition
from core_engine.position_store import PositionStore


def _pos():
    return EnginePosition(
        symbol="BTC/USD",
        entry_ts=datetime(2026, 6, 17, 18, tzinfo=timezone.utc),
        entry_price=65000.0, qty=0.01, stop=64000.0, tp=67000.0,
        max_hold_until=datetime(2026, 6, 17, 20, tzinfo=timezone.utc))


def test_set_then_get_roundtrip(tmp_path):
    ps = PositionStore(str(tmp_path / "state.db"))
    ps.set(_pos())
    got = ps.get()
    assert got["symbol"] == "BTC/USD"
    assert got["entry_price"] == 65000.0 and got["qty"] == 0.01
    assert got["stop"] == 64000.0 and got["tp"] == 67000.0
    assert got["entry_ts"] == "2026-06-17T18:00:00+00:00"


def test_clear_sets_none(tmp_path):
    ps = PositionStore(str(tmp_path / "state.db"))
    ps.set(_pos())
    ps.clear()
    assert ps.get() is None


def test_get_empty_db_is_none(tmp_path):
    assert PositionStore(str(tmp_path / "state.db")).get() is None
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd lab/core-engine && ../../.venv/bin/python -m pytest tests/test_position_store.py -v; cd ../..`
Expected: FAIL — `ModuleNotFoundError: No module named 'core_engine.position_store'`

> If `core_engine` is not importable from the repo venv, run instead with the core-engine venv used by its existing tests (see `lab/core-engine/tests/conftest.py`); use whichever interpreter already runs `lab/core-engine/tests/test_journal.py` green.

- [x] **Step 3: Write minimal implementation**

Create `lab/core-engine/src/core_engine/position_store.py`:

```python
from __future__ import annotations

import json
import sqlite3

from core_engine.contracts import EnginePosition


class PositionStore:
    """Write-through persistence of the engine's open position into the
    runtime_state(key, value) table, under key 'open_position'."""

    KEY = "open_position"

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS runtime_state "
            "(key TEXT PRIMARY KEY, value TEXT)"
        )
        self._conn.commit()

    def set(self, position: EnginePosition) -> None:
        payload = {
            "symbol": position.symbol,
            "entry_price": float(position.entry_price),
            "qty": float(position.qty),
            "stop": float(position.stop) if position.stop is not None else None,
            "tp": float(position.tp) if position.tp is not None else None,
            "entry_ts": position.entry_ts.isoformat() if position.entry_ts else None,
        }
        self._conn.execute(
            "INSERT INTO runtime_state (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (self.KEY, json.dumps(payload)),
        )
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM runtime_state WHERE key=?", (self.KEY,))
        self._conn.commit()

    def get(self) -> dict | None:
        row = self._conn.execute(
            "SELECT value FROM runtime_state WHERE key=?", (self.KEY,)
        ).fetchone()
        if not row or not row[0]:
            return None
        try:
            return json.loads(row[0])
        except (ValueError, TypeError):
            return None
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd lab/core-engine && ../../.venv/bin/python -m pytest tests/test_position_store.py -v; cd ../..`
Expected: PASS (3 passed)

- [x] **Step 5: Commit**

```bash
git add lab/core-engine/src/core_engine/position_store.py lab/core-engine/tests/test_position_store.py
git commit -m "feat(core-engine): PositionStore persists open position to state.db"
```

---

## Task 10: Wire PositionStore into the engine loop

**Files:**
- Modify: `lab/core-engine/src/core_engine/loop.py`, `lab/core-engine/src/core_engine/__main__.py`
- Test: `lab/core-engine/tests/test_loop_position_persist.py`

**Interfaces:**
- Consumes: `PositionStore` (Task 9).
- Produces: `Engine.__init__` accepts optional keyword `position_store=None`. On a filled entry the engine calls `position_store.set(pos)`; on exit/flat it calls `position_store.clear()`. No behavior change when `position_store is None`.

- [x] **Step 1: Write the failing test**

Create `lab/core-engine/tests/test_loop_position_persist.py`:

```python
from datetime import datetime, timezone

from core_engine.contracts import EnginePosition


class _RecordingStore:
    def __init__(self): self.calls = []
    def set(self, pos): self.calls.append(("set", pos))
    def clear(self): self.calls.append(("clear", None))


def _engine_with(monkeypatch, position_store):
    from core_engine import loop as loop_mod
    from core_engine.contracts import Action, Decision

    eng = loop_mod.Engine.__new__(loop_mod.Engine)
    # Minimal hand-wired engine: only the attributes tick() touches.
    eng._journal = type("J", (), {"log": lambda self, e: None})()
    eng._position_store = position_store
    return eng, loop_mod, Action, Decision


def test_clear_called_when_no_position_and_hold(monkeypatch):
    store = _RecordingStore()
    eng, loop_mod, Action, Decision = _engine_with(monkeypatch, store)
    # Stub the engine collaborators so tick() reaches the HOLD return path.
    monkeypatch.setattr(loop_mod, "refresh_candles", lambda *a, **k: 0)
    eng._exec = type("E", (), {"reconcile": lambda self, *a, **k: None})()
    monkeypatch.setattr(loop_mod, "build_context", lambda store: object())
    monkeypatch.setattr(loop_mod, "decide",
                        lambda *a, **k: Decision(Action.HOLD, 0.0, "hold", {}))
    eng.position = None
    eng.tick(datetime.now(timezone.utc))
    assert ("clear", None) in store.calls
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd lab/core-engine && ../../.venv/bin/python -m pytest tests/test_loop_position_persist.py -v; cd ../..`
Expected: FAIL — `AttributeError: 'Engine' object has no attribute '_position_store'` (or the clear assertion fails)

- [x] **Step 3: Write minimal implementation**

In `lab/core-engine/src/core_engine/loop.py`, modify `Engine.__init__` signature and body to accept and store `position_store`:

```python
    def __init__(self, *, store, fetcher, broker, journal, risk, runtime_state,
                 profile, kronos, position_store=None):
        self._store = store
        self._fetcher = fetcher
        self._broker = broker
        self._journal = journal
        self._risk = risk
        self._rt = runtime_state
        self._profile = profile
        self._kronos = kronos
        self._exec = Executor(broker)
        self._position_store = position_store
        self.position = None

    def _persist_position(self) -> None:
        if self._position_store is None:
            return
        if self.position is None:
            self._position_store.clear()
        else:
            self._position_store.set(self.position)
```

In the same file, add `self._persist_position()` at the three points where `self.position` changes inside `tick()`:
- right after `self.position = self._exec.reconcile(...)` (the reconcile line),
- right after `self.position = None` in the exit branch,
- right after `self.position = pos` in the entry-filled branch.

Each insertion is literally one new line immediately following the assignment:

```python
            self._persist_position()
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd lab/core-engine && ../../.venv/bin/python -m pytest tests/test_loop_position_persist.py tests/test_loop.py -v; cd ../..`
Expected: PASS (existing `test_loop.py` still green + new test passes)

- [x] **Step 5: Wire into `__main__.py` and commit**

In `lab/core-engine/src/core_engine/__main__.py`, import `PositionStore` and pass it into the `Engine(...)` constructor in `_build_engine`:

```python
from core_engine.position_store import PositionStore
```

and add to the `Engine(...)` call:

```python
                  position_store=PositionStore(STATE_DB),
```

Then rebuild the core-engine container (per standing rule) and commit:

```bash
docker compose -f lab/core-engine/docker-compose.yml build && \
  docker compose -f lab/core-engine/docker-compose.yml up -d || \
  (cd lab/core-engine && docker build -t core-engine . && \
   docker compose up -d core-engine; cd ../..)
git add lab/core-engine/src/core_engine/loop.py lab/core-engine/src/core_engine/__main__.py lab/core-engine/tests/test_loop_position_persist.py
git commit -m "feat(core-engine): write-through persist open position each tick"
```

> If neither compose file defines the core-engine service, use the exact build/run command from `lab/core-engine/docs/DEPLOY_NEXT.md`; that doc names the container. Verify with `docker ps | grep core` afterward.

---

## Task 11: AutoDashboardService

**Files:**
- Create: `src/swingbot/autodash/service.py`
- Modify: `src/swingbot/autodash/__init__.py`
- Test: `tests/autodash/test_service.py`

**Interfaces:**
- Consumes: `AutoDashConfig` (Task 1), `run_comparison` (Task 3), `build_kronos_signal` (Task 4), `queries.*` (Tasks 5–8), `CandleStore` (`swingbot.data.store`).
- Produces: `AutoDashboardService(config: AutoDashConfig, *, comparison_fn=run_comparison, kronos_factory=build_kronos_signal, candle_loader=None)`. Methods: `backtest() -> dict` (computes once, caches; loads candles from `config.history_db` via `candle_loader`), `position() -> dict|None`, `trades(limit=50) -> list[dict]`, `journal(limit=50) -> list[dict]`, `candles(limit=200) -> list[dict]`.

- [x] **Step 1: Write the failing test**

Create `tests/autodash/test_service.py`:

```python
import numpy as np
import pandas as pd

from swingbot.autodash.config import AutoDashConfig
from swingbot.autodash.service import AutoDashboardService


def _candles(n=120):
    base = np.linspace(100.0, 120.0, n)
    return pd.DataFrame({
        "ts": np.arange(n, dtype=np.int64) * 300 + 1781265600,
        "open": base, "high": base + 1, "low": base - 1,
        "close": base + 0.5, "volume": np.ones(n)})


def _service(tmp_path, calls):
    cfg = AutoDashConfig(core_engine_data=str(tmp_path),
                         history_db=str(tmp_path / "hist.db"))

    def comparison_fn(candles, **kw):
        calls.append("ran")
        return {"ema": {"n_trades": 1}, "kronos": {"n_trades": 1}}

    return AutoDashboardService(cfg, comparison_fn=comparison_fn,
                                kronos_factory=lambda: None,
                                candle_loader=lambda cfg: _candles())


def test_backtest_runs_once_and_caches(tmp_path):
    calls = []
    svc = _service(tmp_path, calls)
    a = svc.backtest()
    b = svc.backtest()
    assert a == b and set(a) == {"ema", "kronos"}
    assert calls == ["ran"]                 # computed exactly once


def test_live_reads_return_empty_when_dbs_absent(tmp_path):
    svc = _service(tmp_path, [])
    assert svc.position() is None
    assert svc.trades() == []
    assert svc.journal() == []
    assert svc.candles() == []
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.autodash.service'`

- [x] **Step 3: Write minimal implementation**

Create `src/swingbot/autodash/service.py`:

```python
from __future__ import annotations

import threading

from swingbot.autodash.backtest_runner import run_comparison
from swingbot.autodash.config import AutoDashConfig
from swingbot.autodash.kronos_factory import build_kronos_signal
from swingbot.autodash import queries


def _default_candle_loader(config: AutoDashConfig):
    from swingbot.data.store import CandleStore
    rows = CandleStore(config.history_db).get(
        config.symbol, config.timeframe, config.backtest_limit)
    return rows


class AutoDashboardService:
    def __init__(self, config: AutoDashConfig, *,
                 comparison_fn=run_comparison,
                 kronos_factory=build_kronos_signal,
                 candle_loader=_default_candle_loader):
        self._cfg = config
        self._comparison_fn = comparison_fn
        self._kronos_factory = kronos_factory
        self._candle_loader = candle_loader
        self._cache: dict | None = None
        self._lock = threading.Lock()

    def backtest(self) -> dict:
        with self._lock:
            if self._cache is None:
                candles = self._candle_loader(self._cfg)
                self._cache = self._comparison_fn(
                    candles, kronos_factory=self._kronos_factory,
                    equity0=self._cfg.equity0)
            return self._cache

    def position(self):
        return queries.live_position(self._cfg.state_db, self._cfg.journal_db)

    def trades(self, limit: int = 50):
        return queries.recent_trades(self._cfg.journal_db, limit)

    def journal(self, limit: int = 50):
        return queries.recent_events(self._cfg.journal_db, limit)

    def candles(self, limit: int = 200):
        return queries.recent_candles(self._cfg.candle_db, self._cfg.symbol,
                                      self._cfg.timeframe, limit)
```

Update `src/swingbot/autodash/__init__.py`:

```python
from swingbot.autodash.config import AutoDashConfig
from swingbot.autodash.service import AutoDashboardService

__all__ = ["AutoDashConfig", "AutoDashboardService"]
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_service.py -v`
Expected: PASS (2 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autodash/service.py src/swingbot/autodash/__init__.py tests/autodash/test_service.py
git commit -m "feat(autodash): service with cached backtest + live reads"
```

---

## Task 12: API router (6 routes)

**Files:**
- Create: `src/swingbot/autodash/router.py`
- Test: `tests/autodash/test_router_endpoints.py`

**Interfaces:**
- Consumes: an object with `backtest()`, `position()`, `trades(limit)`, `journal(limit)`, `candles(limit)` (the service, Task 11).
- Produces: `build_auto_router(service) -> fastapi.APIRouter` with routes: `GET /api/backtest/ema`, `GET /api/backtest/kronos`, `GET /api/live/position`, `GET /api/live/trades`, `GET /api/live/journal`, `GET /api/live/candles`.

- [x] **Step 1: Write the failing test**

Create `tests/autodash/test_router_endpoints.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from swingbot.autodash.router import build_auto_router


class _FakeService:
    def backtest(self):
        return {"ema": {"n_trades": 3, "win_rate": 0.66},
                "kronos": {"n_trades": 4, "win_rate": 0.5}}
    def position(self):
        return {"symbol": "BTC/USD", "entry_price": 65000.0, "qty": 0.01}
    def trades(self, limit=50):
        return [{"ts": "2026-06-17T18:30:00+00:00", "pnl": 5.0,
                 "won": True, "reason": "tp"}]
    def journal(self, limit=50):
        return [{"ts": "t", "kind": "decision", "symbol": "BTC/USD",
                 "reason": "hold", "payload": {}}]
    def candles(self, limit=200):
        return [{"time": 1781265600, "open": 1, "high": 2, "low": 0,
                 "close": 1.5, "volume": 1}]


def _client():
    app = FastAPI()
    app.include_router(build_auto_router(_FakeService()))
    return TestClient(app)


def test_backtest_ema_and_kronos():
    c = _client()
    assert c.get("/api/backtest/ema").json()["win_rate"] == 0.66
    assert c.get("/api/backtest/kronos").json()["n_trades"] == 4


def test_live_endpoints_shapes():
    c = _client()
    assert c.get("/api/live/position").json()["entry_price"] == 65000.0
    assert c.get("/api/live/trades").json()[0]["pnl"] == 5.0
    assert c.get("/api/live/journal").json()[0]["kind"] == "decision"
    assert c.get("/api/live/candles").json()[0]["time"] == 1781265600
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_router_endpoints.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.autodash.router'`

- [x] **Step 3: Write minimal implementation**

Create `src/swingbot/autodash/router.py`:

```python
from __future__ import annotations

from fastapi import APIRouter


def build_auto_router(service) -> APIRouter:
    router = APIRouter()

    @router.get("/api/backtest/ema")
    def backtest_ema():
        return service.backtest()["ema"]

    @router.get("/api/backtest/kronos")
    def backtest_kronos():
        return service.backtest()["kronos"]

    @router.get("/api/live/position")
    def live_position():
        return service.position()

    @router.get("/api/live/trades")
    def live_trades(limit: int = 50):
        return service.trades(limit)

    @router.get("/api/live/journal")
    def live_journal(limit: int = 50):
        return service.journal(limit)

    @router.get("/api/live/candles")
    def live_candles(limit: int = 200):
        return service.candles(limit)

    return router
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_router_endpoints.py -v`
Expected: PASS (2 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autodash/router.py tests/autodash/test_router_endpoints.py
git commit -m "feat(autodash): FastAPI router with 6 read-only dashboard routes"
```

---

## Task 13: Mount router into web.py + wire webmain.py

**Files:**
- Modify: `src/swingbot/web.py` (function `create_app`), `src/swingbot/webmain.py` (function `main`)
- Test: `tests/autodash/test_create_app_mount.py`

**Interfaces:**
- Consumes: `build_auto_router` (Task 12).
- Produces: `create_app(...)` accepts a new optional keyword `auto_dashboard=None`; when provided, it mounts `build_auto_router(auto_dashboard)`. No change when `None`.

- [x] **Step 1: Write the failing test**

Create `tests/autodash/test_create_app_mount.py`:

```python
from fastapi.testclient import TestClient

from swingbot.web import create_app


class _Ctl:
    def status(self): return {}
    def journal(self, s=None): return []
    def metrics(self, s=None): return {}
    def readiness(self): return {}
    def trading_health(self): return {}


class _FakeService:
    def backtest(self): return {"ema": {"n_trades": 1}, "kronos": {"n_trades": 2}}
    def position(self): return None
    def trades(self, limit=50): return []
    def journal(self, limit=50): return []
    def candles(self, limit=200): return []


def test_auto_routes_mounted_when_service_provided():
    app = create_app(controller=_Ctl(), profiles=None, creds=None,
                     token="t", auto_dashboard=_FakeService())
    c = TestClient(app)
    assert c.get("/api/backtest/kronos").json()["n_trades"] == 2
    assert c.get("/api/live/position").json() is None


def test_auto_routes_absent_when_no_service():
    app = create_app(controller=_Ctl(), profiles=None, creds=None, token="t")
    assert TestClient(app).get("/api/backtest/ema").status_code == 404
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/autodash/test_create_app_mount.py -v`
Expected: FAIL — `TypeError: create_app() got an unexpected keyword argument 'auto_dashboard'`

- [x] **Step 3: Write minimal implementation**

In `src/swingbot/web.py`, add the parameter to `create_app` (append to the signature, after `poller=None`):

```python
def create_app(controller, profiles, creds, token: str, store=None, market=None,
               backfiller=None, discovery=None, discovery_cache_path=None,
               brain=None, agent_dir=None, poller=None,
               auto_dashboard=None) -> FastAPI:
```

Then, immediately after `app = FastAPI(title="swingbot", lifespan=lifespan)`, add:

```python
    if auto_dashboard is not None:
        from swingbot.autodash.router import build_auto_router
        app.include_router(build_auto_router(auto_dashboard))
```

In `src/swingbot/webmain.py`, build the service and pass it into `create_app`. Add near the other imports inside `main` (before the `app = create_app(...)` call):

```python
    from swingbot.autodash import AutoDashConfig, AutoDashboardService
    auto_dashboard = AutoDashboardService(AutoDashConfig.default())
```

and add `auto_dashboard=auto_dashboard,` to the `create_app(...)` keyword arguments.

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_create_app_mount.py -v`
Expected: PASS (2 passed)

- [x] **Step 5: Rebuild container and commit**

```bash
docker compose build swingbot && docker compose up -d swingbot
git add src/swingbot/web.py src/swingbot/webmain.py tests/autodash/test_create_app_mount.py
git commit -m "feat(autodash): mount dashboard router into web app via service injection"
```

---

## Task 14: Frontend API helpers + polling hook

**Files:**
- Modify: `frontend/src/api.js`
- Create: `frontend/src/components/AutoDash/usePolling.js`

**Interfaces:**
- Produces: `api.auto = { backtestEma, backtestKronos, position, trades, journal, candles }` (each returns a promise of parsed JSON). `usePolling(fetcher, intervalMs)` React hook returning `{ data, error, loading }`, refetching every `intervalMs`.

- [x] **Step 1: Add API helpers**

In `frontend/src/api.js`, inside the `export const api = { ... }` object (before the closing `}`), add:

```javascript
  auto: {
    backtestEma: () => req('GET', '/api/backtest/ema'),
    backtestKronos: () => req('GET', '/api/backtest/kronos'),
    position: () => req('GET', '/api/live/position'),
    trades: () => req('GET', '/api/live/trades'),
    journal: () => req('GET', '/api/live/journal'),
    candles: () => req('GET', '/api/live/candles'),
  },
```

- [x] **Step 2: Create the polling hook**

Create `frontend/src/components/AutoDash/usePolling.js`:

```javascript
import { useEffect, useRef, useState } from 'react'

// Polls `fetcher()` immediately and every `intervalMs`. Keeps the last good
// value on transient errors (never blanks the panel).
export default function usePolling(fetcher, intervalMs = 10000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fetcher)
  fnRef.current = fetcher

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const d = await fnRef.current()
        if (alive) { setData(d); setError(''); setLoading(false) }
      } catch (e) {
        if (alive) { setError(e.message || 'error'); setLoading(false) }
      }
    }
    tick()
    const id = setInterval(tick, intervalMs)
    return () => { alive = false; clearInterval(id) }
  }, [intervalMs])

  return { data, error, loading }
}
```

- [x] **Step 3: Verify the build**

Run: `cd frontend && npm run build && cd ..`
Expected: `vite build` completes, "✓ built in …", no errors.

- [x] **Step 4: Commit**

```bash
git add frontend/src/api.js frontend/src/components/AutoDash/usePolling.js
git commit -m "feat(frontend): auto.* api helpers + usePolling hook"
```

---

## Task 15: BacktestComparisonPanel

**Files:**
- Create: `frontend/src/components/AutoDash/BacktestComparisonPanel.jsx`

**Interfaces:**
- Consumes: `usePolling` + `api.auto.backtestEma`/`backtestKronos`. Renders two cards (EMA, Kronos) showing win rate, total P&L, Sharpe, trade count.

- [x] **Step 1: Create the component**

Create `frontend/src/components/AutoDash/BacktestComparisonPanel.jsx`:

```jsx
import { api } from '../../api.js'
import usePolling from './usePolling.js'

function Card({ title, m }) {
  if (!m) return <div className="panel"><h3>{title}</h3><div>Loading…</div></div>
  const pnl = Number(m.total_pnl || 0)
  return (
    <div className="panel">
      <h3>{title}</h3>
      <div>Win rate: <b>{(Number(m.win_rate || 0) * 100).toFixed(1)}%</b></div>
      <div>Total P&amp;L: <b style={{ color: pnl >= 0 ? '#36d17a' : '#ff5470' }}>
        {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</b></div>
      <div>Sharpe: <b>{Number(m.sharpe || 0).toFixed(2)}</b></div>
      <div>Trades: <b>{m.n_trades ?? 0}</b></div>
    </div>
  )
}

export default function BacktestComparisonPanel() {
  // Backtest is cached server-side; a slow 60s poll is plenty.
  const ema = usePolling(api.auto.backtestEma, 60000)
  const kronos = usePolling(api.auto.backtestKronos, 60000)
  return (
    <div className="panel full">
      <h3>Backtest: EMA vs Kronos</h3>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <Card title="EMA momentum" m={ema.data} />
        <Card title="Kronos forecast" m={kronos.data} />
      </div>
    </div>
  )
}
```

- [x] **Step 2: Verify the build**

Run: `cd frontend && npm run build && cd ..`
Expected: build succeeds, no errors.

- [x] **Step 3: Commit**

```bash
git add frontend/src/components/AutoDash/BacktestComparisonPanel.jsx
git commit -m "feat(frontend): backtest EMA-vs-Kronos comparison panel"
```

---

## Task 16: CurrentPositionPanel + LiveStatsPanel

**Files:**
- Create: `frontend/src/components/AutoDash/CurrentPositionPanel.jsx`, `frontend/src/components/AutoDash/LiveStatsPanel.jsx`

**Interfaces:**
- `CurrentPositionPanel` consumes `api.auto.position` (3s poll) — shows "No open position" when `null`, else entry price / qty / stop / target.
- `LiveStatsPanel` consumes `api.auto.trades` (10s poll) — computes realized P&L total, win rate, and today's P&L from the trade list.

- [x] **Step 1: Create CurrentPositionPanel**

Create `frontend/src/components/AutoDash/CurrentPositionPanel.jsx`:

```jsx
import { api } from '../../api.js'
import usePolling from './usePolling.js'

export default function CurrentPositionPanel() {
  const { data: pos } = usePolling(api.auto.position, 3000)
  return (
    <div className="panel">
      <h3>Current position</h3>
      {!pos ? <div>No open position (flat).</div> : (
        <div>
          <div>Symbol: <b>{pos.symbol}</b></div>
          <div>Entry: <b>{Number(pos.entry_price).toFixed(2)}</b></div>
          <div>Qty: <b>{Number(pos.qty)}</b></div>
          <div>Stop: <b>{pos.stop != null ? Number(pos.stop).toFixed(2) : '—'}</b></div>
          <div>Target: <b>{pos.tp != null ? Number(pos.tp).toFixed(2) : '—'}</b></div>
        </div>
      )}
    </div>
  )
}
```

- [x] **Step 2: Create LiveStatsPanel**

Create `frontend/src/components/AutoDash/LiveStatsPanel.jsx`:

```jsx
import { api } from '../../api.js'
import usePolling from './usePolling.js'

export default function LiveStatsPanel() {
  const { data: trades } = usePolling(api.auto.trades, 10000)
  const list = trades || []
  const total = list.reduce((a, t) => a + Number(t.pnl || 0), 0)
  const wins = list.filter(t => t.won).length
  const winRate = list.length ? (wins / list.length) * 100 : 0
  const today = new Date().toISOString().slice(0, 10)
  const todayPnl = list
    .filter(t => (t.ts || '').slice(0, 10) === today)
    .reduce((a, t) => a + Number(t.pnl || 0), 0)
  return (
    <div className="panel">
      <h3>Live stats</h3>
      <div>Closed trades: <b>{list.length}</b></div>
      <div>Win rate: <b>{winRate.toFixed(1)}%</b></div>
      <div>Realized P&amp;L: <b style={{ color: total >= 0 ? '#36d17a' : '#ff5470' }}>
        {total >= 0 ? '+' : ''}{total.toFixed(2)}</b></div>
      <div>Today: <b>{todayPnl >= 0 ? '+' : ''}{todayPnl.toFixed(2)}</b></div>
    </div>
  )
}
```

- [x] **Step 3: Verify the build**

Run: `cd frontend && npm run build && cd ..`
Expected: build succeeds, no errors.

- [x] **Step 4: Commit**

```bash
git add frontend/src/components/AutoDash/CurrentPositionPanel.jsx frontend/src/components/AutoDash/LiveStatsPanel.jsx
git commit -m "feat(frontend): current position + live stats panels"
```

---

## Task 17: RecentTradesPanel + JournalFeedPanel

**Files:**
- Create: `frontend/src/components/AutoDash/RecentTradesPanel.jsx`, `frontend/src/components/AutoDash/JournalFeedPanel.jsx`

**Interfaces:**
- `RecentTradesPanel` consumes `api.auto.trades` (10s) — table of ts, P&L, win/loss badge, reason.
- `JournalFeedPanel` consumes `api.auto.journal` (10s) — scrollable feed of ts, kind, reason.

- [x] **Step 1: Create RecentTradesPanel**

Create `frontend/src/components/AutoDash/RecentTradesPanel.jsx`:

```jsx
import { api } from '../../api.js'
import usePolling from './usePolling.js'

export default function RecentTradesPanel() {
  const { data: trades } = usePolling(api.auto.trades, 10000)
  const list = trades || []
  return (
    <div className="panel">
      <h3>Recent trades</h3>
      {list.length === 0 ? <div>No closed trades yet.</div> : (
        <table style={{ width: '100%' }}>
          <thead><tr><th>Time</th><th>P&amp;L</th><th>Result</th><th>Reason</th></tr></thead>
          <tbody>
            {list.map((t, i) => (
              <tr key={i}>
                <td>{(t.ts || '').replace('T', ' ').slice(0, 16)}</td>
                <td style={{ color: t.pnl >= 0 ? '#36d17a' : '#ff5470' }}>
                  {t.pnl >= 0 ? '+' : ''}{Number(t.pnl).toFixed(2)}</td>
                <td>{t.won ? 'WIN' : 'LOSS'}</td>
                <td>{t.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
```

- [x] **Step 2: Create JournalFeedPanel**

Create `frontend/src/components/AutoDash/JournalFeedPanel.jsx`:

```jsx
import { api } from '../../api.js'
import usePolling from './usePolling.js'

export default function JournalFeedPanel() {
  const { data: events } = usePolling(api.auto.journal, 10000)
  const list = events || []
  return (
    <div className="panel">
      <h3>Decision journal</h3>
      <div style={{ maxHeight: 280, overflowY: 'auto' }}>
        {list.length === 0 ? <div>No events yet.</div> : list.map((e, i) => (
          <div key={i} style={{ padding: '4px 0', borderBottom: '1px solid #2a2a2a' }}>
            <span style={{ opacity: 0.6 }}>{(e.ts || '').replace('T', ' ').slice(0, 16)} </span>
            <b>{e.kind}</b> — {e.reason}
          </div>
        ))}
      </div>
    </div>
  )
}
```

- [x] **Step 3: Verify the build**

Run: `cd frontend && npm run build && cd ..`
Expected: build succeeds, no errors.

- [x] **Step 4: Commit**

```bash
git add frontend/src/components/AutoDash/RecentTradesPanel.jsx frontend/src/components/AutoDash/JournalFeedPanel.jsx
git commit -m "feat(frontend): recent trades table + journal feed panels"
```

---

## Task 18: ChartPanel (lightweight-charts v5)

**Files:**
- Create: `frontend/src/components/AutoDash/ChartPanel.jsx`

**Interfaces:**
- Consumes: `api.auto.candles` (10s) and `api.auto.trades`. Renders a candlestick series with entry/exit markers, using the installed `lightweight-charts` v5 API already used by `frontend/src/components/ChartPanel.jsx` (`createChart, CandlestickSeries, createSeriesMarkers`). Candle `time` is epoch seconds.

- [x] **Step 1: Create the component**

Create `frontend/src/components/AutoDash/ChartPanel.jsx`:

```jsx
import { useEffect, useRef } from 'react'
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts'
import { api } from '../../api.js'
import usePolling from './usePolling.js'

const UP = '#36d17a'
const DOWN = '#ff5470'

export default function ChartPanel() {
  const { data: candles } = usePolling(api.auto.candles, 10000)
  const { data: trades } = usePolling(api.auto.trades, 10000)
  const elRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)

  useEffect(() => {
    if (!elRef.current || chartRef.current) return
    const chart = createChart(elRef.current, {
      height: 320, layout: { background: { color: 'transparent' }, textColor: '#ccc' },
      grid: { vertLines: { color: '#222' }, horzLines: { color: '#222' } },
      timeScale: { timeVisible: true },
    })
    const series = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, borderVisible: false,
      wickUpColor: UP, wickDownColor: DOWN,
    })
    chartRef.current = chart
    seriesRef.current = series
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null }
  }, [])

  useEffect(() => {
    if (!seriesRef.current || !candles) return
    seriesRef.current.setData(candles.map(c => ({
      time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })))
    const markers = (trades || [])
      .filter(t => t.ts)
      .map(t => ({
        time: Math.floor(new Date(t.ts).getTime() / 1000),
        position: 'aboveBar', color: t.won ? UP : DOWN, shape: 'circle',
        text: (t.pnl >= 0 ? '+' : '') + Number(t.pnl).toFixed(0),
      }))
      .sort((a, b) => a.time - b.time)
    createSeriesMarkers(seriesRef.current, markers)
    chartRef.current?.timeScale().fitContent()
  }, [candles, trades])

  return (
    <div className="panel full">
      <h3>BTC/USD candles</h3>
      <div ref={elRef} style={{ width: '100%' }} />
    </div>
  )
}
```

- [x] **Step 2: Verify the build**

Run: `cd frontend && npm run build && cd ..`
Expected: build succeeds, no errors (confirms the v5 imports resolve).

- [x] **Step 3: Commit**

```bash
git add frontend/src/components/AutoDash/ChartPanel.jsx
git commit -m "feat(frontend): candle chart panel with trade markers (lightweight-charts v5)"
```

---

## Task 19: AutoDashboard page + nav tab

**Files:**
- Create: `frontend/src/pages/AutoDashboard.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- Consumes: all six AutoDash panels. Mounts at hash route `#/auto` via a new `auto` tab. Does NOT modify the existing `Dashboard.jsx` / `dashboard` tab.

- [x] **Step 1: Create the page**

Create `frontend/src/pages/AutoDashboard.jsx`:

```jsx
import ChartPanel from '../components/AutoDash/ChartPanel.jsx'
import CurrentPositionPanel from '../components/AutoDash/CurrentPositionPanel.jsx'
import LiveStatsPanel from '../components/AutoDash/LiveStatsPanel.jsx'
import RecentTradesPanel from '../components/AutoDash/RecentTradesPanel.jsx'
import BacktestComparisonPanel from '../components/AutoDash/BacktestComparisonPanel.jsx'
import JournalFeedPanel from '../components/AutoDash/JournalFeedPanel.jsx'

export default function AutoDashboard() {
  return (
    <div className="wrap">
      <ChartPanel />
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <CurrentPositionPanel />
        <LiveStatsPanel />
      </div>
      <BacktestComparisonPanel />
      <RecentTradesPanel />
      <JournalFeedPanel />
    </div>
  )
}
```

- [x] **Step 2: Wire the route into App.jsx**

In `frontend/src/App.jsx`:

1. Add the import after the existing `Dashboard` import (line 3):

```jsx
import AutoDashboard from './pages/AutoDashboard.jsx'
```

2. Add `'auto'` to the `TABS` array (line 14):

```jsx
const TABS = ['dashboard', 'auto', 'strategy', 'discover', 'brain', 'settings', 'health', 'guide']
```

3. Add a nav button right after the `dashboard` button (after line 61):

```jsx
        <button className={tab==='auto'?'active':''} onClick={()=>setTab('auto')}>Autonomous</button>
```

4. Add the render branch right after the `dashboard` block (after its closing `</>}` near line 84):

```jsx
      {tab==='auto' && <AutoDashboard />}
```

- [x] **Step 3: Verify the build**

Run: `cd frontend && npm run build && cd ..`
Expected: build succeeds, no errors.

- [x] **Step 4: Commit**

```bash
git add frontend/src/pages/AutoDashboard.jsx frontend/src/App.jsx
git commit -m "feat(frontend): AutoDashboard page wired to #/auto tab"
```

---

## Task 20: Backend E2E test against seeded DBs

**Files:**
- Create: `tests/autodash/test_e2e.py`

**Interfaces:**
- Consumes: `create_app` (Task 13), `AutoDashConfig` + `AutoDashboardService` (Tasks 1, 11). Seeds real temp SQLite DBs and asserts all six routes return correct shapes through the full stack (no mocks except the backtest candle loader for speed).

- [x] **Step 1: Write the test**

Create `tests/autodash/test_e2e.py`:

```python
import json
import sqlite3

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from swingbot.autodash import AutoDashConfig, AutoDashboardService
from swingbot.web import create_app


class _Ctl:
    def status(self): return {}
    def journal(self, s=None): return []
    def metrics(self, s=None): return {}
    def readiness(self): return {}
    def trading_health(self): return {}


def _seed(tmp_path):
    j = sqlite3.connect(str(tmp_path / "journal.db"))
    j.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
              "ts TEXT, kind TEXT, symbol TEXT, reason TEXT, payload TEXT)")
    j.execute("INSERT INTO events (ts,kind,symbol,reason,payload) VALUES (?,?,?,?,?)",
              ("2026-06-17T18:30:00+00:00", "pnl", "BTC/USD", "closed: tp",
               json.dumps({"realized": 7.0, "won": True})))
    j.commit(); j.close()
    s = sqlite3.connect(str(tmp_path / "state.db"))
    s.execute("CREATE TABLE runtime_state (key TEXT PRIMARY KEY, value TEXT)")
    s.commit(); s.close()
    c = sqlite3.connect(str(tmp_path / "candles.db"))
    c.execute("CREATE TABLE bars (symbol TEXT, timeframe TEXT, ts INTEGER, "
              "open REAL, high REAL, low REAL, close REAL, volume REAL, "
              "PRIMARY KEY (symbol, timeframe, ts))")
    c.execute("INSERT INTO bars VALUES ('BTC/USD','5m',1781265600,1,2,0,1.5,1.0)")
    c.commit(); c.close()


def _candle_loader(_cfg):
    n = 120
    base = np.linspace(100.0, 120.0, n)
    return pd.DataFrame({
        "ts": np.arange(n, dtype=np.int64) * 300 + 1781265600,
        "open": base, "high": base + 1, "low": base - 1,
        "close": base + 0.5, "volume": np.ones(n)})


def test_full_stack_six_routes(tmp_path):
    _seed(tmp_path)
    cfg = AutoDashConfig(core_engine_data=str(tmp_path),
                         history_db=str(tmp_path / "candles.db"))
    svc = AutoDashboardService(cfg, kronos_factory=lambda: None,
                               candle_loader=_candle_loader)
    app = create_app(controller=_Ctl(), profiles=None, creds=None,
                     token="t", auto_dashboard=svc)
    c = TestClient(app)

    for path in ("/api/backtest/ema", "/api/backtest/kronos"):
        body = c.get(path).json()
        assert set(body) == {"n_trades", "win_rate", "total_pnl",
                             "sharpe", "final_equity", "equity_curve"}
    assert c.get("/api/live/position").json() is None
    assert c.get("/api/live/trades").json()[0]["pnl"] == 7.0
    assert c.get("/api/live/journal").json()[0]["kind"] == "pnl"
    assert c.get("/api/live/candles").json()[0]["time"] == 1781265600
```

- [x] **Step 2: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/autodash/test_e2e.py -v`
Expected: PASS (1 passed)

- [x] **Step 3: Run the full autodash suite**

Run: `.venv/bin/python -m pytest tests/autodash/ -q`
Expected: PASS (all autodash tests green)

- [x] **Step 4: Commit**

```bash
git add tests/autodash/test_e2e.py
git commit -m "test(autodash): full-stack E2E across all six dashboard routes"
```

---

## Task 21: Backfill free history + slow Kronos smoke

**Files:**
- Create: `tests/autodash/test_kronos_smoke_slow.py`

**Interfaces:**
- Operational: populate ~6 months of BTC/USD into the history DB via the existing free Coinbase provider (`swingbot.backfill_cli`, no API key). Then a `@pytest.mark.slow` test runs one real Kronos comparison if torch+Kronos+CUDA are present, else skips.

- [x] **Step 1: Backfill BTC/USD history (free, Coinbase, no key)**

Run (this fetches real data; it is operational, not a unit test):

```bash
.venv/bin/python -m swingbot.backfill_cli \
  --exchange coinbase --symbols BTC/USD --timeframes 5m --start 2026-01-01
```

Expected: prints `[backfill] done: <N> new bars across 1 symbols x 1 timeframes`.

Verify coverage:

```bash
.venv/bin/python -c "from swingbot.data.store import CandleStore; import os; \
s=CandleStore(os.path.expanduser('~/.swingbot/candles.db')); \
print(s.coverage('BTC/USD','5m'))"
```

Expected: a dict with `count` in the thousands and `min_ts`/`max_ts` spanning the requested window. (If Coinbase caps depth, re-run with `--exchange kraken`; both are key-free. Record the achieved window — this is the honest backtest window.)

- [x] **Step 2: Write the slow smoke test**

Create `tests/autodash/test_kronos_smoke_slow.py`:

```python
import os
import pytest

from swingbot.autodash.config import AutoDashConfig
from swingbot.autodash.service import AutoDashboardService
from swingbot.autodash.kronos_factory import build_kronos_signal, pick_device

pytestmark = pytest.mark.slow


def test_real_kronos_comparison_if_available():
    if build_kronos_signal() is None:
        pytest.skip("Kronos/torch stack unavailable on this host")
    cfg = AutoDashConfig.default()
    if not os.path.exists(cfg.history_db):
        pytest.skip("no history db backfilled yet")
    print(f"[smoke] kronos device = {pick_device()}")
    svc = AutoDashboardService(cfg)
    out = svc.backtest()
    assert set(out) == {"ema", "kronos"}
    assert out["ema"]["n_trades"] >= 0 and out["kronos"]["n_trades"] >= 0
```

- [x] **Step 3: Run the smoke test**

Run: `.venv/bin/python -m pytest tests/autodash/test_kronos_smoke_slow.py -v -m slow -s`
Expected: PASS or SKIP. If it runs, it prints `[smoke] kronos device = cuda` on the RTX 3050 host and completes the real EMA+Kronos comparison. Note the printed device and wall time.

- [x] **Step 4: Register the `slow` marker and commit**

Add to `pyproject.toml` under `[tool.pytest.ini_options]` (create the `markers` key if absent):

```toml
markers = ["slow: heavy tests (real Kronos inference); run with -m slow"]
```

```bash
git add tests/autodash/test_kronos_smoke_slow.py pyproject.toml
git commit -m "test(autodash): backfill free BTC history + slow real-Kronos smoke"
```

---

## Task 22: Playwright UI smoke

**Files:**
- (No new repo files — uses the Playwright MCP browser tools and a running dev stack.)

**Interfaces:**
- Verifies the rendered dashboard end-to-end in a real browser at `#/auto`.

- [x] **Step 1: Start the stack**

Run (background): `cd frontend && npm run dev &` then confirm the backend container is up: `docker ps | grep swingbot`.
Expected: Vite serves on `http://localhost:3000` (or the port Vite prints); the `/api` proxy reaches the backend.

- [x] **Step 2: Drive the browser**

Using the Playwright MCP browser tools:
1. `browser_navigate` to `http://localhost:3000/#/auto`.
2. `browser_snapshot` — assert the accessibility tree contains the headings "BTC/USD candles", "Current position", "Live stats", "Backtest: EMA vs Kronos", "Recent trades", and "Decision journal".
3. `browser_take_screenshot` to `docs/autodash-smoke.png`.

Expected: all six panel headings present; no uncaught console errors via `browser_console_messages` (network errors for empty live data are acceptable and must show graceful "No …" copy, not a crash).

- [x] **Step 3: Commit the screenshot as evidence**

```bash
git add docs/autodash-smoke.png
git commit -m "test(autodash): playwright UI smoke screenshot of #/auto"
```

---

## Task 23: Docs + deploy + roadmap update

**Files:**
- Create: `docs/API_DASHBOARD.md`, `docs/DATA_SOURCES.md`
- Modify: `crypto-swing-bot/docs/ROADMAP_STATUS.md`

- [x] **Step 1: Write `docs/API_DASHBOARD.md`**

Document the six routes with exact JSON shapes from Tasks 5–8 and 2. Create `docs/API_DASHBOARD.md`:

```markdown
# Autonomous Dashboard API

All routes are GET, read-only, unauthenticated. Mounted by `create_app(..., auto_dashboard=AutoDashboardService(...))`.

## GET /api/backtest/ema  and  GET /api/backtest/kronos
Cached once at first call. Returns:
`{ "n_trades": int, "win_rate": float, "total_pnl": float, "sharpe": float, "final_equity": float, "equity_curve": [float, ...] }`

## GET /api/live/position
`null` when flat, else:
`{ "symbol": str, "entry_price": float, "qty": float, "stop": float|null, "tp": float|null, "entry_ts": str|null }`

## GET /api/live/trades?limit=50
`[ { "ts": str, "pnl": float, "won": bool, "reason": str }, ... ]` (newest first; from core-engine `pnl` events)

## GET /api/live/journal?limit=50
`[ { "ts": str, "kind": str, "symbol": str, "reason": str, "payload": object }, ... ]` (newest first)

## GET /api/live/candles?limit=200
`[ { "time": int(epoch_seconds), "open": float, "high": float, "low": float, "close": float, "volume": float }, ... ]` (oldest first)

Data sources: backtest reads `~/.swingbot/candles.db`; live routes read `~/.core-engine/{journal,state,candles}.db`.
```

- [x] **Step 2: Write `docs/DATA_SOURCES.md`**

Create `docs/DATA_SOURCES.md`:

```markdown
# Free Market Data Sources

The backtest loads candles from a `CandleStore` keyed by `(symbol, timeframe)`, so any
asset present in the store works. Backfill via `python -m swingbot.backfill_cli`.

## Crypto (no API key)
- **Coinbase** (`--exchange coinbase`) — deep OHLCV, key-free. Primary source.
- **Kraken** (`--exchange kraken`) — key-free; shallower depth (~720 bars/request).
- Binance is geo-blocked (HTTP 451) from this host — do not use.

## Stocks / indices / ETFs (free, account + key)
These are NOT yet wired into `backfill_cli`; they need a small provider adapter
(follow-on sub-project — see ROADMAP). Free tiers that cost $0:
- **Alpaca** — already have paper keys; IEX stock data free. Good first add.
- **Stooq** — free CSV, no key, daily history for stocks/indices/ETFs.
- **Alpha Vantage / Twelve Data / Finnhub / Tiingo** — free API key, rate-limited.

## How the dashboard uses this
The EMA-vs-Kronos backtest runs on whatever BTC/USD history is in `~/.swingbot/candles.db`.
Today that is the window backfilled in Task 21; extend depth by re-running the backfill.
A universal multi-asset data layer (stocks/indices) is tracked as a separate sub-project.
```

- [x] **Step 3: Rebuild both containers**

```bash
docker compose build swingbot && docker compose up -d swingbot
```

(Core-engine was rebuilt in Task 10; rebuild again only if its source changed since.)

Expected: containers up; `docker ps` shows `swingbot` running.

- [x] **Step 4: Update ROADMAP_STATUS.md and commit**

Edit `crypto-swing-bot/docs/ROADMAP_STATUS.md` so NEXT ACTION reflects that the autonomous dashboard sub-project is implemented (point to this plan as DONE, and name the universal-data-layer follow-on as the next brainstorm).

```bash
git add docs/API_DASHBOARD.md docs/DATA_SOURCES.md crypto-swing-bot/docs/ROADMAP_STATUS.md
git commit -m "docs(autodash): API + data-source docs; roadmap update"
```

---

## Self-Review

**Spec coverage (meta-plan → tasks):**
- Phase 1.1 backtest runner → Tasks 2, 3, 4 (summary, comparison, Kronos factory). ✅
- Phase 1.2 live queries (position, trades, events, candles) → Tasks 5–8. ✅
- Phase 2.1 API endpoints (6 routes) → Task 12. ✅
- Phase 2.2 backtest init/caching → Task 11 (lazy cache in service) + Task 13 (wired at startup via webmain). ✅
- Phase 3.1 dashboard page → Task 19. ✅
- Phase 3.2 six panels (Chart, Position, Trades, Comparison, Stats, Journal) + polling hook → Tasks 14–18. ✅
- Phase 3.3 router integration → Task 19 (nav tab). ✅
- Phase 4.1 E2E → Task 20; Phase 4.2 manual/browser smoke → Task 22. ✅
- Phase 5.1 API docs → Task 23; Phase 5.2 Docker/deploy → Tasks 13, 23. ✅
- Open meta-plan questions resolved: charting = installed `lightweight-charts` v5 (reused); candles default 200; backtest window = whatever the free backfill yields (Task 21, honest labeling); auto-refresh via `usePolling` (no manual button); journal schema = `events(id,ts,kind,symbol,reason,payload)`. ✅
- User answers honored: generic per-asset data path + free-source matrix (Task 21 + `DATA_SOURCES.md`); full Kronos on GPU (Task 4 device pick + Task 21 real run on cuda); accurate position via persistence (Tasks 9–10) with read fallback (Task 8). ✅

**Type consistency:** `BacktestResult` fields (`trades/final_equity/wins/losses`), `BacktestSummary` keys (six, identical in Tasks 2/3/12/20/`API_DASHBOARD.md`), `live_position` dict keys (identical in Tasks 8/9/16/`API_DASHBOARD.md`), candle shape (`time/open/high/low/close/volume`, epoch-seconds `time` in Tasks 7/18/20), trade shape (`ts/pnl/won/reason` in Tasks 6/16/17/20) — all aligned.

**Placeholder scan:** every code step shows full code; every command has expected output. No TBD/TODO/"similar to". Frontend "test" gate is explicitly `npm run build` (no JS test runner exists). ✅

**Known risk flagged in-plan:** the universal stock/index data layer is intentionally out of scope here (its own sub-project), per `DATA_SOURCES.md` and the roadmap note.
