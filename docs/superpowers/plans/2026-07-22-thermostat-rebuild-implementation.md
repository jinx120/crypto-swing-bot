# Thermostat Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the app as a thermostat — the user sets two things (which coins, how much risk); everything else (strategy params, drawdown response, sizing) is automated and invisible.

**Architecture:** Keep the entire backend infrastructure (FastAPI, SQLite stores, Alpaca, Coinbase, Kronos, orchestrator, telemetry). Add two engine-room services — `RiskProfile` (three named param sets) and `AutoTuner` (drawdown-driven auto-tightening, backed by a new equity time-series store) — expose them through thin new endpoints, replace the entire React frontend with a 3-screen thermostat UI, and delete the user-facing tuning surface (LLM advisor, rebalance controls, researched presets, per-strategy parameter editing).

**Tech Stack:** Python 3 / FastAPI / SQLite / pandas (backend); React 18 + Vite + Tailwind v3 + hand-authored shadcn-style primitives + react-router-dom v6 (frontend). Deployed via Docker on the swingbot VM.

**Scope note:** This plan covers spec §8 items 1–5 (the deployable thermostat product). Spec §8 items 6–7 (signal research in `lab/`: 4h EMA, funding-rate, on-chain flows) are an explicitly parallel/non-blocking research track and get their own plan later. The thermostat wraps the **existing** Kronos-bracket strategy; no new signal is required to ship.

## Global Constraints

- Python interpreter: **`.venv/bin/python`** (plain `python`/`pytest` are not on PATH).
- Test gate: `.venv/bin/python -m pytest -q` — last known baseline **533 passed, 5 skipped** (2026-06-25). Every backend task keeps the suite green (adapt existing tests, never delete coverage — spec §7).
- Lint gate: `.venv/bin/ruff check src/` must be clean.
- Frontend gates: `cd frontend && npm run build` (must succeed) and `npm run test` (Vitest, must pass).
- After any `src/` change run `python3 -m graphify update .` to keep the graph current (AST-only, no API cost).
- **Docker rebuild after every code change (standing rule, pre-authorized):** `docker compose build swingbot && docker compose up -d swingbot`. The running container does not pick up source changes otherwise.
- Working on `master` is user-approved. Scope each `git add` to the task's files; the tree may carry unrelated uncommitted work that must stay untouched.
- SQLite stores all live in the one data-dir DB `~/.swingbot/swingbot.db` unless noted; `state_db` is that path.
- Risk-controlled profile keys (the only fields RiskProfile/AutoTuner ever write): `max_position_frac`, `entry_threshold`, `tp_pct`, `sl_pct`, `max_concurrent`, `cooldown_minutes`. `sl_pct`/`tp_pct` are stored as **positive magnitudes** (existing convention: `sl_pct=0.005` means a −0.5% stop).
- Risk level names are exactly `"Conservative"`, `"Moderate"`, `"Aggressive"` (default `"Moderate"`). Keep them capitalized everywhere — API, store, and UI.

---

## File Structure

**New backend files**
- `src/swingbot/risk_profile.py` — the three named param sets + helpers (`RISK_LEVELS`, `risk_params`, `apply_risk_level`, `DRAWDOWN_SENSITIVITY`).
- `src/swingbot/equity_store.py` — `EquitySnapshotStore`: append-only portfolio equity time-series + rolling-window drawdown/pnl.
- `src/swingbot/autotuner.py` — `AutoTuner` + `TuneDecision`: pure drawdown→tier policy.

**Modified backend files**
- `src/swingbot/profiles.py` — add `get_risk_level`/`set_risk_level`.
- `src/swingbot/web.py` — add `/api/risk-level`, `/api/coins`, `/api/portfolio/pnl`; remove advisor/rebalance-write/researched endpoints (Task 14).
- `src/swingbot/supervisor.py` — wire equity store + AutoTuner into `__init__`/`tick_all`/`_build_summary`; remove advisor plumbing (Task 14).
- `src/swingbot/webmain.py` — drop advisor wiring (Task 14).

**New frontend files**
- `frontend/src/pages/Home.jsx`, `frontend/src/pages/Coins.jsx`, `frontend/src/pages/SettingsScreen.jsx`
- `frontend/src/lib/format.js` + `frontend/src/lib/format.test.js` — pure display helpers (Vitest-tested).

**Deleted frontend files** (Task 13): `pages/MissionControl.jsx`, `pages/CoinDetail.jsx`, `pages/Settings.jsx`, and all now-orphaned components under `components/` (`CoinCard`, `CoinsGrid`, `LiveJournal`, `RebalancePanel`, `RebalanceStrip`, `StatusStrip`, `AddCoinDialog`, `AdvisorNotes`, `MiniChart`, `useLivePrice`, everything in `components/detail/`, and `components/settings/{RiskDialPanel,TuningJournalPanel,DataSourcePanel,AdvancedControls}.jsx`). `components/settings/BrokerConnectionPanel.jsx` and `components/ui/*` are retained.

---

## Phase 1 — RiskProfile abstraction (backend)

### Task 1: RiskProfile param sets

**Files:**
- Create: `src/swingbot/risk_profile.py`
- Test: `tests/test_risk_profile.py`

**Interfaces:**
- Produces: `RISK_LEVELS: tuple[str, ...]`, `DEFAULT_RISK_LEVEL: str`, `risk_params(level: str) -> dict`, `apply_risk_level(profile: dict, level: str) -> dict`, `DRAWDOWN_SENSITIVITY: dict[str, str]`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_risk_profile.py
import pytest

from swingbot.risk_profile import (
    RISK_LEVELS, DEFAULT_RISK_LEVEL, risk_params, apply_risk_level,
    DRAWDOWN_SENSITIVITY,
)


def test_levels_and_default():
    assert RISK_LEVELS == ("Conservative", "Moderate", "Aggressive")
    assert DEFAULT_RISK_LEVEL == "Moderate"


def test_risk_params_values_match_spec():
    assert risk_params("Conservative")["max_position_frac"] == 0.05
    assert risk_params("Moderate")["entry_threshold"] == 0.50
    assert risk_params("Aggressive")["max_concurrent"] == 4
    # sl/tp stored as positive magnitudes
    assert risk_params("Conservative")["sl_pct"] == 0.005
    assert risk_params("Aggressive")["tp_pct"] == 0.020


def test_risk_params_unknown_level_raises():
    with pytest.raises(ValueError):
        risk_params("YOLO")


def test_apply_risk_level_overwrites_only_risk_keys():
    profile = {"symbol": "BTC/USD", "signals": {"kronos_forecast": {"weight": 1.0}},
               "entry_threshold": 0.05, "max_position_frac": 0.25}
    out = apply_risk_level(profile, "Conservative")
    assert out["symbol"] == "BTC/USD"                     # untouched
    assert out["signals"] == {"kronos_forecast": {"weight": 1.0}}  # untouched
    assert out["entry_threshold"] == 0.70                 # overwritten
    assert out["max_position_frac"] == 0.05               # overwritten
    assert profile["entry_threshold"] == 0.05             # original not mutated


def test_drawdown_sensitivity():
    assert DRAWDOWN_SENSITIVITY == {
        "Conservative": "HIGH", "Moderate": "MEDIUM", "Aggressive": "LOW"}
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_risk_profile.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.risk_profile'`

- [x] **Step 3: Write minimal implementation**

```python
# src/swingbot/risk_profile.py
from __future__ import annotations

# The three named risk levels the user picks on the Coins screen. Each maps to a
# full internal StrategyProfile param set (spec §5a). The user never sees the
# numbers — they pick a name. Only the risk-controlled keys are defined here;
# symbol/signals/timeframe/etc. stay on the per-coin profile.
RISK_LEVELS = ("Conservative", "Moderate", "Aggressive")
DEFAULT_RISK_LEVEL = "Moderate"

_PARAMS: dict[str, dict] = {
    "Conservative": {
        "max_position_frac": 0.05,
        "entry_threshold": 0.70,
        "tp_pct": 0.008,
        "sl_pct": 0.005,
        "max_concurrent": 1,
        "cooldown_minutes": 60,
    },
    "Moderate": {
        "max_position_frac": 0.10,
        "entry_threshold": 0.50,
        "tp_pct": 0.012,
        "sl_pct": 0.008,
        "max_concurrent": 2,
        "cooldown_minutes": 30,
    },
    "Aggressive": {
        "max_position_frac": 0.20,
        "entry_threshold": 0.30,
        "tp_pct": 0.020,
        "sl_pct": 0.015,
        "max_concurrent": 4,
        "cooldown_minutes": 0,
    },
}

# Consumed by the AutoTuner (how aggressively to react to drawdown), NOT written
# to the strategy profile.
DRAWDOWN_SENSITIVITY = {
    "Conservative": "HIGH",
    "Moderate": "MEDIUM",
    "Aggressive": "LOW",
}


def risk_params(level: str) -> dict:
    """The risk-controlled param overlay for a named level. Fresh dict each call."""
    if level not in _PARAMS:
        raise ValueError(f"unknown risk level {level!r}")
    return dict(_PARAMS[level])


def apply_risk_level(profile: dict, level: str) -> dict:
    """Return a COPY of `profile` with the level's risk params applied. Non-risk
    keys (symbol, signals, timeframe, ...) are preserved; input is not mutated."""
    merged = dict(profile)
    merged.update(risk_params(level))
    return merged
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_risk_profile.py -q`
Expected: PASS (5 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/risk_profile.py tests/test_risk_profile.py
git commit -m "feat: RiskProfile named param sets (Conservative/Moderate/Aggressive)"
```

---

### Task 2: ProfileStore risk-level persistence

**Files:**
- Modify: `src/swingbot/profiles.py`
- Test: `tests/test_profiles_meta.py`

**Interfaces:**
- Consumes: `risk_profile.RISK_LEVELS` / `DEFAULT_RISK_LEVEL` (Task 1).
- Produces: `ProfileStore.get_risk_level() -> str`, `ProfileStore.set_risk_level(level: str) -> None`.

- [x] **Step 1: Write the failing test** (append to `tests/test_profiles_meta.py`)

```python
def test_risk_level_defaults_to_moderate(tmp_path):
    from swingbot.profiles import ProfileStore
    store = ProfileStore(str(tmp_path / "p.db"))
    assert store.get_risk_level() == "Moderate"


def test_set_and_get_risk_level(tmp_path):
    from swingbot.profiles import ProfileStore
    store = ProfileStore(str(tmp_path / "p.db"))
    store.set_risk_level("Aggressive")
    assert store.get_risk_level() == "Aggressive"


def test_set_risk_level_rejects_unknown(tmp_path):
    import pytest
    from swingbot.profiles import ProfileStore
    store = ProfileStore(str(tmp_path / "p.db"))
    with pytest.raises(ValueError):
        store.set_risk_level("reckless")
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_profiles_meta.py -q -k risk_level`
Expected: FAIL with `AttributeError: 'ProfileStore' object has no attribute 'get_risk_level'`

- [x] **Step 3: Write minimal implementation** — add to `ProfileStore` (after `set_risk_dial`, near line 96 of `src/swingbot/profiles.py`):

```python
    _RISK_LEVELS = ("Conservative", "Moderate", "Aggressive")

    def get_risk_level(self) -> str:
        return self.get_meta("risk_level") or "Moderate"

    def set_risk_level(self, level: str) -> None:
        if level not in self._RISK_LEVELS:
            raise ValueError(f"unknown risk_level {level!r}")
        self.set_meta("risk_level", level)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_profiles_meta.py -q -k risk_level`
Expected: PASS (3 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/profiles.py tests/test_profiles_meta.py
git commit -m "feat: ProfileStore.get/set_risk_level meta persistence"
```

---

### Task 3: `/api/risk-level` endpoint

**Files:**
- Modify: `src/swingbot/web.py`
- Test: `tests/test_risk_level_api.py`

**Interfaces:**
- Consumes: `ProfileStore.get_risk_level/set_risk_level` (Task 2), `risk_profile.risk_params`/`RISK_LEVELS` (Task 1), existing `controller.reload()`.
- Produces: `GET /api/risk-level` → `{"risk_level": str, "choices": [...]}`; `PUT /api/risk-level` body `{"risk_level": str}` → applies the level's params to every armed profile, resets the AutoTuner overlay, reloads.

- [x] **Step 1: Write the failing test**

```python
# tests/test_risk_level_api.py
from fastapi.testclient import TestClient

from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class _Ctl:
    def __init__(self):
        self.reloaded = 0
    def reload(self):
        self.reloaded += 1
    def status(self):
        return {}


def _app(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    profiles.save("kronos-btc-usd", {"symbol": "BTC/USD",
                  "signals": {"kronos_forecast": {"weight": 1.0}},
                  "entry_threshold": 0.05, "max_position_frac": 0.25})
    profiles.arm("kronos-btc-usd")
    ctl = _Ctl()
    app = create_app(controller=ctl, profiles=profiles, creds=None, token="")
    return TestClient(app), profiles, ctl


def test_get_risk_level_default(tmp_path):
    client, _, _ = _app(tmp_path)
    body = client.get("/api/risk-level").json()
    assert body["risk_level"] == "Moderate"
    assert body["choices"] == ["Conservative", "Moderate", "Aggressive"]


def test_put_risk_level_applies_params_to_armed(tmp_path):
    client, profiles, ctl = _app(tmp_path)
    res = client.put("/api/risk-level", json={"risk_level": "Conservative"})
    assert res.status_code == 200
    p = profiles.get("kronos-btc-usd")
    assert p["entry_threshold"] == 0.70
    assert p["max_position_frac"] == 0.05
    assert p["symbol"] == "BTC/USD"            # non-risk keys preserved
    assert profiles.get_risk_level() == "Conservative"
    assert profiles.get_meta("autotuner_tier") == "0"   # overlay reset
    assert ctl.reloaded >= 1


def test_put_risk_level_rejects_unknown(tmp_path):
    client, _, _ = _app(tmp_path)
    assert client.put("/api/risk-level", json={"risk_level": "nope"}).status_code == 400
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_risk_level_api.py -q`
Expected: FAIL (404 on `/api/risk-level`)

- [x] **Step 3: Write minimal implementation** — in `src/swingbot/web.py`:

Add import near the other `swingbot` imports (top of file):

```python
from swingbot.risk_profile import RISK_LEVELS, risk_params
```

Add a request model next to the other `BaseModel`s (near `RiskDialBody`):

```python
class RiskLevelBody(BaseModel):
    risk_level: str
```

Add the endpoints inside `create_app` (place near the `/api/risk-dial` block):

```python
    @app.get("/api/risk-level")
    def get_risk_level():
        return {"risk_level": profiles.get_risk_level(), "choices": list(RISK_LEVELS)}

    @app.put("/api/risk-level")
    def put_risk_level(body: RiskLevelBody, _=Depends(require_token)):
        try:
            profiles.set_risk_level(body.risk_level)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        params = risk_params(body.risk_level)
        for name in profiles.list_armed():
            pdict = profiles.get(name)
            if pdict is None:
                continue
            pdict.update(params)
            profiles.save(name, pdict)
        # A manual level change re-baselines: clear any AutoTuner tightening so the
        # next cycle re-derives the tier from live drawdown against the new baseline.
        profiles.set_meta("autotuner_tier", "0")
        profiles.set_meta("autotuner_status", "")
        controller.reload()
        return {"ok": True, "risk_level": body.risk_level}
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_risk_level_api.py -q`
Expected: PASS (3 passed)

- [x] **Step 5: Full gate + rebuild + commit**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
python3 -m graphify update .
docker compose build swingbot && docker compose up -d swingbot
git add src/swingbot/web.py tests/test_risk_level_api.py
git commit -m "feat: /api/risk-level GET/PUT applies named risk params to armed strategies"
```

---

## Phase 2 — AutoTuner (backend)

### Task 4: EquitySnapshotStore

**Files:**
- Create: `src/swingbot/equity_store.py`
- Test: `tests/test_equity_store.py`

**Interfaces:**
- Produces: `EquitySnapshotStore(db_path)` with `record(equity: float, now: datetime|None=None)`, `drawdown(hours: float, now=None) -> float` (fraction of the rolling-window peak the current equity sits below, 0..1), `pnl_window(hours: float, now=None) -> tuple[float, float]` (abs, pct vs window-start equity), `prune(keep_days=30.0, now=None)`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_equity_store.py
from datetime import datetime, timezone, timedelta

from swingbot.equity_store import EquitySnapshotStore


def _t(h):
    return datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc) - timedelta(hours=h)


def test_drawdown_zero_when_empty(tmp_path):
    s = EquitySnapshotStore(str(tmp_path / "e.db"))
    assert s.drawdown(24) == 0.0


def test_drawdown_from_window_peak(tmp_path):
    s = EquitySnapshotStore(str(tmp_path / "e.db"))
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    s.record(10000.0, now - timedelta(hours=20))   # peak in window
    s.record(9600.0, now - timedelta(hours=1))     # current: 4% below peak
    assert round(s.drawdown(24, now), 4) == 0.04


def test_drawdown_ignores_data_outside_window(tmp_path):
    s = EquitySnapshotStore(str(tmp_path / "e.db"))
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    s.record(20000.0, now - timedelta(hours=48))   # old peak, outside 24h window
    s.record(10000.0, now - timedelta(hours=2))
    s.record(9900.0, now - timedelta(hours=1))
    assert round(s.drawdown(24, now), 4) == 0.01    # peak inside window is 10000


def test_pnl_window(tmp_path):
    s = EquitySnapshotStore(str(tmp_path / "e.db"))
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    s.record(10000.0, now - timedelta(hours=23))
    s.record(10300.0, now - timedelta(minutes=5))
    abs_pnl, pct = s.pnl_window(24, now)
    assert round(abs_pnl, 2) == 300.0
    assert round(pct, 4) == 0.03
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_equity_store.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.equity_store'`

- [x] **Step 3: Write minimal implementation**

```python
# src/swingbot/equity_store.py
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone


class EquitySnapshotStore:
    """Append-only portfolio-equity time-series. Backs the AutoTuner's rolling
    drawdown check and the Home screen's P&L windows. One row per trading cycle."""

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS equity_snapshots "
            "(ts TEXT NOT NULL, equity REAL NOT NULL)")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_equity_ts ON equity_snapshots(ts)")
        self._conn.commit()

    def record(self, equity: float, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        self._conn.execute(
            "INSERT INTO equity_snapshots (ts, equity) VALUES (?, ?)",
            (now.isoformat(), float(equity)))
        self._conn.commit()

    def _window(self, hours: float, now: datetime | None) -> list[float]:
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(hours=hours)).isoformat()
        rows = self._conn.execute(
            "SELECT equity FROM equity_snapshots WHERE ts >= ? ORDER BY ts",
            (cutoff,)).fetchall()
        return [r[0] for r in rows]

    def drawdown(self, hours: float, now: datetime | None = None) -> float:
        """How far below the window's peak the current (latest) equity sits, as a
        fraction in [0, 1]. 0.0 when there is no data or we are at/above the peak."""
        eqs = self._window(hours, now)
        if not eqs:
            return 0.0
        peak = max(eqs)
        current = eqs[-1]
        if peak <= 0:
            return 0.0
        return max(0.0, (peak - current) / peak)

    def pnl_window(self, hours: float, now: datetime | None = None) -> tuple[float, float]:
        """(absolute, fractional) P&L of the latest equity vs the window-start
        equity. (0.0, 0.0) when the window has fewer than two points."""
        eqs = self._window(hours, now)
        if len(eqs) < 2:
            return 0.0, 0.0
        start, current = eqs[0], eqs[-1]
        abs_pnl = current - start
        pct = (abs_pnl / start) if start else 0.0
        return abs_pnl, pct

    def prune(self, keep_days: float = 30.0, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        cutoff = (now - timedelta(days=keep_days)).isoformat()
        self._conn.execute("DELETE FROM equity_snapshots WHERE ts < ?", (cutoff,))
        self._conn.commit()
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_equity_store.py -q`
Expected: PASS (4 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/equity_store.py tests/test_equity_store.py
git commit -m "feat: EquitySnapshotStore (rolling drawdown + P&L windows)"
```

---

### Task 5: AutoTuner policy

**Files:**
- Create: `src/swingbot/autotuner.py`
- Test: `tests/test_autotuner.py`

**Interfaces:**
- Consumes: `risk_profile.risk_params` (Task 1).
- Produces: `AutoTuner()` with `decide(level: str, dd_24h: float, dd_7d: float, current_tier: int = 0) -> TuneDecision`; `TuneDecision(tier: int, defensive: bool, status: str, params: dict)`.

Policy (spec §5b): escalate to tier 1 when 24h drawdown > 3%, tier 2 when 7d drawdown > 8%; de-escalate only after real recovery (24h dd < 1% and 7d dd < 4%) — hysteresis prevents flapping. Tier 1 tightens: `max_position_frac ×0.7`, `entry_threshold ×1.2`, `max_concurrent −1` (floor 1). Tier 2 additionally suspends new entries by setting `entry_threshold` unreachably high (existing decision path then records SIGNAL_BELOW_THRESHOLD; open positions still manage/exit normally).

- [x] **Step 1: Write the failing test**

```python
# tests/test_autotuner.py
from swingbot.autotuner import AutoTuner


def test_normal_tier_is_baseline():
    d = AutoTuner().decide("Moderate", dd_24h=0.0, dd_7d=0.0)
    assert d.tier == 0
    assert d.defensive is False
    assert d.status == ""
    assert d.params["max_position_frac"] == 0.10
    assert d.params["entry_threshold"] == 0.50


def test_tighten_on_24h_drawdown():
    d = AutoTuner().decide("Moderate", dd_24h=0.04, dd_7d=0.0)
    assert d.tier == 1
    assert d.defensive is True
    assert round(d.params["max_position_frac"], 4) == 0.07     # 0.10 * 0.7
    assert round(d.params["entry_threshold"], 4) == 0.60       # 0.50 * 1.2
    assert d.params["max_concurrent"] == 1                     # 2 - 1
    assert "Defensive" in d.status


def test_suspend_on_7d_drawdown():
    d = AutoTuner().decide("Aggressive", dd_24h=0.10, dd_7d=0.09)
    assert d.tier == 2
    assert d.params["entry_threshold"] >= 999.0               # no new entries pass
    assert d.params["max_concurrent"] == 3                     # 4 - 1
    assert d.defensive is True


def test_hysteresis_holds_tier_until_recovered():
    tuner = AutoTuner()
    # still 2% down in 24h -> stays tightened even though below the 3% trigger
    d = tuner.decide("Moderate", dd_24h=0.02, dd_7d=0.02, current_tier=1)
    assert d.tier == 1
    # recovered below 1% -> relaxes to baseline
    d2 = tuner.decide("Moderate", dd_24h=0.005, dd_7d=0.01, current_tier=1)
    assert d2.tier == 0


def test_max_concurrent_floor_is_one():
    d = AutoTuner().decide("Conservative", dd_24h=0.05, dd_7d=0.0)  # base max_concurrent 1
    assert d.params["max_concurrent"] == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_autotuner.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'swingbot.autotuner'`

- [x] **Step 3: Write minimal implementation**

```python
# src/swingbot/autotuner.py
from __future__ import annotations

from dataclasses import dataclass

from swingbot.risk_profile import risk_params

# Tier-1 tightening multipliers (spec §5b).
_POS_FRAC_MULT = 0.7        # reduce max_position_frac 30%
_THRESH_MULT = 1.2         # raise entry_threshold 20%
_SUSPEND_THRESHOLD = 999.0  # tier 2: unreachable -> no new entries pass

# Thresholds.
_TIGHTEN_24H = 0.03
_SUSPEND_7D = 0.08
_RECOVER_24H = 0.01
_RECOVER_7D = 0.04

_STATUS = {
    0: "",
    1: "Defensive mode — recovering from recent losses.",
    2: "Defensive mode — new trades paused while recovering.",
}


@dataclass(frozen=True)
class TuneDecision:
    tier: int            # 0 normal, 1 tightened, 2 suspend-new-entries
    defensive: bool      # tier >= 1 (Home shows a status note)
    status: str          # human string for the Home screen
    params: dict         # effective risk-key overlay to persist onto armed profiles


class AutoTuner:
    """Pure drawdown->tier policy. No I/O: the caller supplies drawdown metrics and
    the current risk level + tier, and persists the returned param overlay."""

    def decide(self, level: str, dd_24h: float, dd_7d: float,
               current_tier: int = 0) -> TuneDecision:
        tier = int(current_tier)
        # Escalate on breach.
        if dd_7d > _SUSPEND_7D:
            tier = 2
        elif dd_24h > _TIGHTEN_24H:
            tier = max(tier, 1)
        # De-escalate only after genuine recovery (hysteresis).
        if tier == 2 and dd_7d < _RECOVER_7D and dd_24h < _RECOVER_24H:
            tier = 1
        if tier == 1 and dd_24h < _RECOVER_24H and dd_7d < _RECOVER_7D:
            tier = 0

        base = risk_params(level)
        params = dict(base)
        if tier >= 1:
            params["max_position_frac"] = round(base["max_position_frac"] * _POS_FRAC_MULT, 6)
            params["entry_threshold"] = round(base["entry_threshold"] * _THRESH_MULT, 6)
            params["max_concurrent"] = max(1, base["max_concurrent"] - 1)
        if tier == 2:
            params["entry_threshold"] = _SUSPEND_THRESHOLD
        return TuneDecision(tier=tier, defensive=tier >= 1,
                            status=_STATUS[tier], params=params)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_autotuner.py -q`
Expected: PASS (5 passed)

- [x] **Step 5: Commit**

```bash
git add src/swingbot/autotuner.py tests/test_autotuner.py
git commit -m "feat: AutoTuner drawdown->tier policy (tighten/suspend/recover)"
```

---

### Task 6: Wire equity store + AutoTuner into the supervisor

**Files:**
- Modify: `src/swingbot/supervisor.py`
- Test: `tests/test_supervisor_autotuner.py`

**Interfaces:**
- Consumes: `EquitySnapshotStore` (Task 4), `AutoTuner` (Task 5), `ProfileStore.get_risk_level` (Task 2), existing `self.reload()`, `self.profiles`, `self._build_summary`.
- Produces: `PortfolioSupervisor._maybe_autotune(now)`, `PortfolioSupervisor._apply_effective_params(params)`; `_build_summary` gains `defensive` (bool) + `autotuner_status` (str); each cycle records equity to the snapshot store.

- [x] **Step 1: Write the failing test**

```python
# tests/test_supervisor_autotuner.py
from datetime import datetime, timezone

from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor


def _sup(tmp_path):
    profiles = ProfileStore(str(tmp_path / "swingbot.db"))
    profiles.save("kronos-btc-usd", {"symbol": "BTC/USD",
                  "signals": {"kronos_forecast": {"weight": 1.0}},
                  "entry_threshold": 0.50, "max_position_frac": 0.10,
                  "max_concurrent": 2})
    profiles.arm("kronos-btc-usd")
    profiles.set_risk_level("Moderate")
    sup = PortfolioSupervisor(profiles=profiles, creds=None,
                              state_db=str(tmp_path / "swingbot.db"))
    return sup, profiles


def test_autotune_tightens_armed_profiles_on_drawdown(tmp_path):
    sup, profiles = _sup(tmp_path)
    now = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
    # Seed an equity dip: 24h peak 10000 -> current 9600 (4% down).
    from datetime import timedelta
    sup._equity_snapshots.record(10000.0, now - timedelta(hours=10))
    sup._equity_snapshots.record(9600.0, now - timedelta(minutes=1))
    sup._maybe_autotune(now)
    p = profiles.get("kronos-btc-usd")
    assert round(p["max_position_frac"], 4) == 0.07
    assert round(p["entry_threshold"], 4) == 0.60
    assert profiles.get_meta("autotuner_tier") == "1"
    assert sup._defensive_mode is True


def test_summary_exposes_defensive_flag(tmp_path):
    sup, _ = _sup(tmp_path)
    sup._defensive_mode = True
    sup._autotuner_status = "Defensive mode — recovering from recent losses."
    summary = sup._build_summary({"equity": 10000.0})
    assert summary["defensive"] is True
    assert "Defensive" in summary["autotuner_status"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_supervisor_autotuner.py -q`
Expected: FAIL with `AttributeError: 'PortfolioSupervisor' object has no attribute '_equity_snapshots'`

- [x] **Step 3: Write minimal implementation** in `src/swingbot/supervisor.py`:

Add imports at the top with the other `swingbot` imports:

```python
from swingbot.equity_store import EquitySnapshotStore
from swingbot.autotuner import AutoTuner
```

In `__init__` (after `self._trade_store = TradeStore(state_db)`, ~line 154) add:

```python
        self._equity_snapshots = EquitySnapshotStore(state_db)
        self._autotuner = AutoTuner()
        self._defensive_mode = False
        self._autotuner_status = ""
```

Add the two methods (place next to `_maybe_run_advisor`, ~line 503):

```python
    def _maybe_autotune(self, now: datetime) -> None:
        """Drawdown-driven auto-tightening. Runs once per cycle; only rewrites the
        armed profiles when the tier actually changes (spec §5b). Never raises."""
        try:
            level = self.profiles.get_risk_level()
            cur_tier = int(self.profiles.get_meta("autotuner_tier") or 0)
            dd_24h = self._equity_snapshots.drawdown(24, now)
            dd_7d = self._equity_snapshots.drawdown(24 * 7, now)
            decision = self._autotuner.decide(level, dd_24h, dd_7d, cur_tier)
            self._defensive_mode = decision.defensive
            self._autotuner_status = decision.status
            if decision.tier != cur_tier:
                self.profiles.set_meta("autotuner_tier", str(decision.tier))
                self.profiles.set_meta("autotuner_status", decision.status)
                self._apply_effective_params(decision.params)
        except Exception as exc:  # auto-tuning must never break a trading cycle
            print(f"[supervisor] autotune skipped: {exc}")

    def _apply_effective_params(self, params: dict) -> None:
        """Persist the effective risk overlay onto every armed profile, then reload
        so the live orchestrators pick it up. `params` holds absolute values derived
        from the risk-level baseline, so this restores baseline when tier returns 0."""
        for name in self.profiles.list_armed():
            pdict = self.profiles.get(name)
            if pdict is None:
                continue
            pdict.update(params)
            self.profiles.save(name, pdict)
        self.reload()
```

In `tick_all`, replace the tail (lines ~499–501):

```python
        self._maybe_run_advisor()
        if acct is not None:
            self._summary = self._build_summary(acct)
```

with:

```python
        if acct is not None:
            self._equity_snapshots.record(acct["equity"], now)
            self._maybe_autotune(now)
            self._summary = self._build_summary(acct)
```

(The `_maybe_run_advisor()` call is removed here; the advisor is deleted wholesale in Task 14.)

In `_build_summary` (~line 722) add two keys to the returned dict:

```python
            "kill_switch": {"active": prs.kill_switch_active, "reason": prs.kill_switch_reason},
            "defensive": self._defensive_mode,
            "autotuner_status": self._autotuner_status,
        }
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_supervisor_autotuner.py -q`
Expected: PASS (2 passed)

- [x] **Step 5: Full gate + rebuild + commit**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
python3 -m graphify update .
docker compose build swingbot && docker compose up -d swingbot
git add src/swingbot/supervisor.py tests/test_supervisor_autotuner.py
git commit -m "feat: wire EquitySnapshotStore + AutoTuner into supervisor tick loop"
```

---

### Task 7: `/api/portfolio/pnl` endpoint (Home P&L windows)

**Files:**
- Modify: `src/swingbot/web.py`, `src/swingbot/webmain.py`
- Test: `tests/test_portfolio_pnl_api.py`

**Interfaces:**
- Consumes: `EquitySnapshotStore.pnl_window` (Task 4).
- Produces: `GET /api/portfolio/pnl` → `{"24h": {"abs": float, "pct": float}, "7d": {...}, "30d": {...}}`. `create_app` gains an optional `equity_store=None` kwarg; when absent the route returns zeros.

- [x] **Step 1: Write the failing test**

```python
# tests/test_portfolio_pnl_api.py
from datetime import datetime, timezone, timedelta

from fastapi.testclient import TestClient

from swingbot.equity_store import EquitySnapshotStore
from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class _Ctl:
    def status(self):
        return {}


def test_pnl_windows(tmp_path):
    es = EquitySnapshotStore(str(tmp_path / "e.db"))
    now = datetime.now(timezone.utc)
    es.record(10000.0, now - timedelta(hours=20))
    es.record(10500.0, now - timedelta(minutes=1))
    profiles = ProfileStore(str(tmp_path / "p.db"))
    app = create_app(controller=_Ctl(), profiles=profiles, creds=None, token="",
                     equity_store=es)
    body = TestClient(app).get("/api/portfolio/pnl").json()
    assert round(body["24h"]["abs"], 2) == 500.0
    assert round(body["24h"]["pct"], 4) == 0.05
    assert "7d" in body and "30d" in body


def test_pnl_zero_without_store(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    app = create_app(controller=_Ctl(), profiles=profiles, creds=None, token="")
    body = TestClient(app).get("/api/portfolio/pnl").json()
    assert body["24h"] == {"abs": 0.0, "pct": 0.0}
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_portfolio_pnl_api.py -q`
Expected: FAIL (`create_app() got an unexpected keyword argument 'equity_store'`)

- [x] **Step 3: Write minimal implementation**

In `src/swingbot/web.py`, extend the `create_app` signature:

```python
def create_app(controller, profiles, creds, token: str, store=None, market=None,
               backfiller=None, poller=None, advisor_journal=None,
               auto_dashboard=None, equity_store=None) -> FastAPI:
```

Add the endpoint (near `/api/state`):

```python
    @app.get("/api/portfolio/pnl")
    def portfolio_pnl():
        windows = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}
        if equity_store is None:
            return {k: {"abs": 0.0, "pct": 0.0} for k in windows}
        out = {}
        for label, hours in windows.items():
            abs_pnl, pct = equity_store.pnl_window(hours)
            out[label] = {"abs": abs_pnl, "pct": pct}
        return out
```

In `src/swingbot/webmain.py`, create the store and pass it through. After `supervisor = PortfolioSupervisor(...)` reuse the supervisor's store instance so both read/write the same table:

```python
    app = create_app(controller=supervisor, profiles=profiles, creds=creds,
                     token=token, store=store, market=market, backfiller=backfiller,
                     poller=poller, advisor_journal=advisor_journal,
                     auto_dashboard=auto_dashboard,
                     equity_store=supervisor._equity_snapshots)
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_portfolio_pnl_api.py -q`
Expected: PASS (2 passed)

- [x] **Step 5: Full gate + rebuild + commit**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
python3 -m graphify update .
docker compose build swingbot && docker compose up -d swingbot
git add src/swingbot/web.py src/swingbot/webmain.py tests/test_portfolio_pnl_api.py
git commit -m "feat: /api/portfolio/pnl 24h/7d/30d windows from equity snapshots"
```

---

## Phase 3 — Coin onboarding automation (backend)

### Task 8: `/api/coins` add / remove / list

**Files:**
- Modify: `src/swingbot/web.py`
- Test: `tests/test_coins_api.py`

**Interfaces:**
- Consumes: `kronos_bracket_profile` (existing), `risk_profile.risk_params` + `ProfileStore.get_risk_level` (Tasks 1–2), existing `_kronos_profile_name`, `controller.reload()`, `controller.flatten(name)`.
- Produces: `GET /api/coins` → `[{"name","symbol"}]`; `POST /api/coins` body `{"symbol"}` → creates a Kronos profile at the current risk level, arms it, reloads; `DELETE /api/coins/{name}` → flattens + disarms + reloads.

- [x] **Step 1: Write the failing test**

```python
# tests/test_coins_api.py
from fastapi.testclient import TestClient

from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class _Ctl:
    def __init__(self):
        self.flattened = []
        self.reloaded = 0
    def reload(self):
        self.reloaded += 1
    def flatten(self, name=None):
        self.flattened.append(name)
    def status(self):
        return {}


def _app(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    profiles.set_risk_level("Conservative")
    ctl = _Ctl()
    return TestClient(create_app(controller=ctl, profiles=profiles, creds=None,
                                 token="")), profiles, ctl


def test_add_coin_creates_armed_profile_at_risk_level(tmp_path):
    client, profiles, ctl = _app(tmp_path)
    res = client.post("/api/coins", json={"symbol": "btc"})
    assert res.status_code == 200
    name = res.json()["name"]
    assert res.json()["symbol"] == "BTC/USD"
    assert name in profiles.list_armed()
    p = profiles.get(name)
    assert p["symbol"] == "BTC/USD"
    assert p["entry_threshold"] == 0.70          # Conservative applied
    assert p["max_position_frac"] == 0.05
    assert p["signals"]["kronos_forecast"]["weight"] == 1.0
    assert ctl.reloaded >= 1


def test_list_coins(tmp_path):
    client, _, _ = _app(tmp_path)
    client.post("/api/coins", json={"symbol": "ETH/USD"})
    coins = client.get("/api/coins").json()
    assert coins == [{"name": "kronos-eth-usd", "symbol": "ETH/USD"}]


def test_remove_coin_flattens_and_disarms(tmp_path):
    client, profiles, ctl = _app(tmp_path)
    client.post("/api/coins", json={"symbol": "BTC/USD"})
    res = client.delete("/api/coins/kronos-btc-usd")
    assert res.status_code == 200
    assert "kronos-btc-usd" not in profiles.list_armed()
    assert "kronos-btc-usd" in ctl.flattened


def test_remove_unknown_coin_404(tmp_path):
    client, _, _ = _app(tmp_path)
    assert client.delete("/api/coins/kronos-doge-usd").status_code == 404
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_coins_api.py -q`
Expected: FAIL (404 on `/api/coins`)

- [x] **Step 3: Write minimal implementation** in `src/swingbot/web.py`:

Add a request model (near the other `BaseModel`s):

```python
class CoinBody(BaseModel):
    symbol: str
```

Add the endpoints (place near the `/api/watchlist` block):

```python
    @app.get("/api/coins")
    def list_coins():
        out = []
        for name in profiles.list_armed():
            p = profiles.get(name) or {}
            out.append({"name": name, "symbol": p.get("symbol")})
        return out

    @app.post("/api/coins")
    def add_coin(body: CoinBody, _=Depends(require_token)):
        symbol = body.symbol.strip().upper()
        if not symbol:
            raise HTTPException(status_code=400, detail="symbol is required")
        if "/" not in symbol:
            symbol = f"{symbol}/USD"
        name = _kronos_profile_name(symbol)
        profile = kronos_bracket_profile(symbol)
        profile.update(risk_params(profiles.get_risk_level()))
        try:
            profiles.save(name, profile)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        profiles.arm(name)
        controller.reload()
        return {"name": name, "symbol": symbol}

    @app.delete("/api/coins/{name}")
    def remove_coin(name: str, _=Depends(require_token)):
        if name not in profiles.list_armed():
            raise HTTPException(status_code=404, detail=f"coin {name!r} not armed")
        controller.flatten(name)
        profiles.disarm(name)
        controller.reload()
        return {"ok": True}
```

- [x] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_coins_api.py -q`
Expected: PASS (4 passed)

- [x] **Step 5: Full gate + rebuild + commit**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
python3 -m graphify update .
docker compose build swingbot && docker compose up -d swingbot
git add src/swingbot/web.py tests/test_coins_api.py
git commit -m "feat: /api/coins add/remove/list (risk-level-aware onboarding)"
```

---

## Phase 4 — Thermostat frontend (3 screens)

> Frontend follows the repo's established pattern: pure display logic lives in `lib/` and is Vitest-tested; screen components are verified by `npm run build` + an MCP/Playwright smoke (no per-component unit tests, matching `docs/redesign-smoke.png` precedent).

### Task 9: API client methods + P&L formatter

**Files:**
- Modify: `frontend/src/api.js`
- Create: `frontend/src/lib/format.js`, `frontend/src/lib/format.test.js`

**Interfaces:**
- Produces: `api.riskLevel()`, `api.setRiskLevel(level)`, `api.coins()`, `api.addCoin(symbol)`, `api.removeCoin(name)`, `api.portfolioPnl()`; `formatMoney(n)`, `formatSignedPct(frac)`, `formatSignedMoney(n)`.

- [x] **Step 1: Write the failing test**

```javascript
// frontend/src/lib/format.test.js
import { describe, it, expect } from 'vitest'
import { formatMoney, formatSignedPct, formatSignedMoney } from './format.js'

describe('format', () => {
  it('formats money with two decimals and separators', () => {
    expect(formatMoney(10842.334)).toBe('$10,842.33')
  })
  it('formats signed percent from a fraction', () => {
    expect(formatSignedPct(0.032)).toBe('+3.2%')
    expect(formatSignedPct(-0.004)).toBe('-0.4%')
  })
  it('formats signed money', () => {
    expect(formatSignedMoney(342)).toBe('+$342.00')
    expect(formatSignedMoney(-12)).toBe('-$12.00')
  })
})
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/lib/format.test.js`
Expected: FAIL (cannot resolve `./format.js`)

- [x] **Step 3: Write minimal implementation**

```javascript
// frontend/src/lib/format.js
export function formatMoney(n) {
  const v = Number(n || 0)
  return '$' + v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export function formatSignedPct(frac) {
  const pct = Number(frac || 0) * 100
  const sign = pct >= 0 ? '+' : '-'
  return `${sign}${Math.abs(pct).toFixed(1)}%`
}

export function formatSignedMoney(n) {
  const v = Number(n || 0)
  const sign = v >= 0 ? '+' : '-'
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
```

Then append these methods to the `api` object in `frontend/src/api.js` (before the closing `}` of the export, after the `watchlist` block; also delete the `advisor`, `risk-dial`, `researched`, and `rebalance` client methods — those endpoints are removed in Task 14, so drop lines 63–65 and 68–84):

```javascript
  // --- thermostat ---
  riskLevel: () => req('GET', '/api/risk-level'),
  setRiskLevel: (risk_level) => req('PUT', '/api/risk-level', { risk_level }),
  coins: () => req('GET', '/api/coins'),
  addCoin: (symbol) => req('POST', '/api/coins', { symbol }),
  removeCoin: (name) => req('DELETE', `/api/coins/${encodeURIComponent(name)}`),
  portfolioPnl: () => req('GET', '/api/portfolio/pnl'),
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/lib/format.test.js`
Expected: PASS (3 passed)

- [x] **Step 5: Commit**

```bash
git add frontend/src/api.js frontend/src/lib/format.js frontend/src/lib/format.test.js
git commit -m "feat: thermostat API client methods + P&L formatters"
```

---

### Task 10: Home screen

**Files:**
- Create: `frontend/src/pages/Home.jsx`

**Interfaces:**
- Consumes: `api.state()`, `api.portfolioPnl()`, `api.decisions(undefined, 8)`, `api.control('start'|'stop')`, `api.price(symbols)`; `formatMoney`/`formatSignedPct`/`formatSignedMoney`; ui primitives `Button`, `Card`.
- Produces: default-exported `Home` component.

Wireframe (spec §4 Screen 1): running badge + Stop/Start; portfolio value + P&L with 24h/7d/30d tabs; open positions; recent activity; the defensive-mode note when `portfolio.defensive`.

- [x] **Step 1: Create the component**

```jsx
// frontend/src/pages/Home.jsx
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card } from '../components/ui/card.jsx'
import { Button } from '../components/ui/button.jsx'
import { formatMoney, formatSignedPct, formatSignedMoney } from '../lib/format.js'

const WINDOWS = ['24h', '7d', '30d']

export default function Home() {
  const [state, setState] = useState(null)
  const [pnl, setPnl] = useState(null)
  const [recent, setRecent] = useState([])
  const [window, setWindow] = useState('24h')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function refresh() {
    try {
      const [s, p, d] = await Promise.all([
        api.state(), api.portfolioPnl(), api.decisions(undefined, 8),
      ])
      setState(s); setPnl(p); setRecent(d || []); setErr('')
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [])

  const portfolio = state?.portfolio || {}
  const running = !!portfolio.running
  const strategies = state?.strategies || []
  const positions = strategies.filter((s) => s.position)
  const win = pnl?.[window] || { abs: 0, pct: 0 }

  async function toggle() {
    setBusy(true)
    try { await api.control(running ? 'stop' : 'start'); await refresh() }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="mx-auto max-w-md space-y-4 p-4">
      <div className="flex items-center justify-between">
        <span className={`inline-flex items-center gap-2 text-sm font-medium ${running ? 'text-emerald-500' : 'text-muted-foreground'}`}>
          <span className={`h-2 w-2 rounded-full ${running ? 'bg-emerald-500' : 'bg-muted-foreground'}`} />
          {running ? 'Running' : 'Stopped'}
        </span>
        <Button variant={running ? 'destructive' : 'default'} disabled={busy} onClick={toggle}>
          {running ? 'Stop' : 'Start'}
        </Button>
      </div>

      {err && <div className="text-sm text-red-500">{err}</div>}

      <Card className="space-y-3 p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">Portfolio</div>
        <div className="text-3xl font-semibold">{formatMoney(portfolio.equity)}</div>
        <div className={`text-sm ${win.abs >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
          {formatSignedMoney(win.abs)} ({formatSignedPct(win.pct)})
        </div>
        <div className="flex gap-2">
          {WINDOWS.map((w) => (
            <button key={w} onClick={() => setWindow(w)}
              className={`rounded-md px-2.5 py-1 text-xs ${w === window ? 'bg-accent text-foreground' : 'text-muted-foreground'}`}>
              {w}
            </button>
          ))}
        </div>
        {portfolio.defensive && (
          <div className="rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-500">
            {portfolio.autotuner_status || 'Defensive mode — recovering from recent losses.'}
          </div>
        )}
      </Card>

      <Card className="space-y-2 p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">Open Positions</div>
        {positions.length === 0 && <div className="text-sm text-muted-foreground">No open positions.</div>}
        {positions.map((s) => {
          const pos = s.position
          const up = (pos.unrealized ?? 0) >= 0
          return (
            <div key={s.name} className="flex items-center justify-between text-sm">
              <span className="font-medium">{s.symbol}</span>
              <span className="text-muted-foreground">{Number(pos.qty).toFixed(4)}</span>
              <span>{pos.mark_price ? formatMoney(pos.qty * pos.mark_price) : '—'}</span>
              <span className={up ? 'text-emerald-500' : 'text-red-500'}>
                {pos.unrealized != null ? formatSignedMoney(pos.unrealized) : '—'}
              </span>
            </div>
          )
        })}
      </Card>

      <Card className="space-y-2 p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">Recent Activity</div>
        {recent.length === 0 && <div className="text-sm text-muted-foreground">Nothing yet.</div>}
        {recent.map((d, i) => (
          <div key={i} className="flex items-center justify-between text-sm">
            <span className="font-medium">{(d.strategy || '').replace('kronos-', '').replace('-', '/').toUpperCase()}</span>
            <span className="text-muted-foreground">{d.decision_code}</span>
            <span className="text-xs text-muted-foreground">{d.bar_ts ? new Date(d.bar_ts).toLocaleTimeString() : ''}</span>
          </div>
        ))}
      </Card>
    </div>
  )
}
```

- [x] **Step 2: Verify it builds**

Run: `cd frontend && npm run build`
Expected: build succeeds (App.jsx still references old pages until Task 13 — that's fine; this task only adds a file and does not remove imports).

- [x] **Step 3: Commit**

```bash
git add frontend/src/pages/Home.jsx
git commit -m "feat: thermostat Home screen (P&L, positions, activity, defensive note)"
```

---

### Task 11: Coins screen

**Files:**
- Create: `frontend/src/pages/Coins.jsx`

**Interfaces:**
- Consumes: `api.coins()`, `api.addCoin(symbol)`, `api.removeCoin(name)`, `api.riskLevel()`, `api.setRiskLevel(level)`; ui `Card`, `Button`, `Input`.
- Produces: default-exported `Coins` component.

- [x] **Step 1: Create the component**

```jsx
// frontend/src/pages/Coins.jsx
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card } from '../components/ui/card.jsx'
import { Button } from '../components/ui/button.jsx'
import { Input } from '../components/ui/input.jsx'

export default function Coins() {
  const [coins, setCoins] = useState([])
  const [level, setLevel] = useState('Moderate')
  const [choices, setChoices] = useState(['Conservative', 'Moderate', 'Aggressive'])
  const [symbol, setSymbol] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function refresh() {
    try {
      const [c, r] = await Promise.all([api.coins(), api.riskLevel()])
      setCoins(c || [])
      setLevel(r.risk_level)
      setChoices(r.choices || choices)
      setErr('')
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { refresh() }, [])

  async function add(e) {
    e.preventDefault()
    if (!symbol.trim()) return
    setBusy(true)
    try { await api.addCoin(symbol.trim()); setSymbol(''); await refresh() }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function remove(name) {
    setBusy(true)
    try { await api.removeCoin(name); await refresh() }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function pickLevel(l) {
    setBusy(true)
    try { await api.setRiskLevel(l); setLevel(l) }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="mx-auto max-w-md space-y-4 p-4">
      {err && <div className="text-sm text-red-500">{err}</div>}

      <Card className="space-y-3 p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">Trading</div>
        {coins.length === 0 && <div className="text-sm text-muted-foreground">No coins yet.</div>}
        {coins.map((c) => (
          <div key={c.name} className="flex items-center justify-between text-sm">
            <span className="inline-flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              {c.symbol}
            </span>
            <button className="text-muted-foreground hover:text-red-500"
              disabled={busy} onClick={() => remove(c.name)}>×</button>
          </div>
        ))}
        <form onSubmit={add} className="flex gap-2 pt-2">
          <Input placeholder="Add coin (e.g. SOL)" value={symbol}
            onChange={(e) => setSymbol(e.target.value)} />
          <Button type="submit" disabled={busy}>Add</Button>
        </form>
      </Card>

      <Card className="space-y-2 p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">Risk Level</div>
        {choices.map((l) => (
          <label key={l} className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="radio" name="risk" checked={l === level} disabled={busy}
              onChange={() => pickLevel(l)} />
            {l}
          </label>
        ))}
      </Card>
    </div>
  )
}
```

- [x] **Step 2: Verify it builds**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [x] **Step 3: Commit**

```bash
git add frontend/src/pages/Coins.jsx
git commit -m "feat: thermostat Coins screen (add/remove coin + risk level)"
```

---

### Task 12: Settings screen

**Files:**
- Create: `frontend/src/pages/SettingsScreen.jsx`

**Interfaces:**
- Consumes: existing `components/settings/BrokerConnectionPanel.jsx`; `api.control('mode', {mode})`, `api.state()`; ui `Card`.
- Produces: default-exported `SettingsScreen` component. Broker panel (reused), paper/live mode toggle, notifications placeholder (spec §4 Screen 3).

- [x] **Step 1: Create the component**

```jsx
// frontend/src/pages/SettingsScreen.jsx
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card } from '../components/ui/card.jsx'
import BrokerConnectionPanel from '../components/settings/BrokerConnectionPanel.jsx'

export default function SettingsScreen() {
  const [mode, setMode] = useState('paper')
  const [err, setErr] = useState('')

  useEffect(() => {
    api.state().then((s) => setMode(s?.portfolio?.mode || 'paper')).catch(() => {})
  }, [])

  async function pickMode(m) {
    try { await api.control('mode', { mode: m }); setMode(m); setErr('') }
    catch (e) { setErr(e.message) }
  }

  return (
    <div className="mx-auto max-w-md space-y-4 p-4">
      {err && <div className="text-sm text-red-500">{err}</div>}

      <Card className="p-4">
        <div className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">Broker</div>
        <BrokerConnectionPanel />
      </Card>

      <Card className="space-y-2 p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">Mode</div>
        {['paper', 'live'].map((m) => (
          <label key={m} className="flex cursor-pointer items-center gap-2 text-sm capitalize">
            <input type="radio" name="mode" checked={m === mode} onChange={() => pickMode(m)} />
            {m} trading
          </label>
        ))}
      </Card>

      <Card className="space-y-2 p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">Notifications (optional)</div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input type="checkbox" disabled /> Trade alerts (coming soon)
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input type="checkbox" disabled /> Drawdown warnings (coming soon)
        </label>
      </Card>
    </div>
  )
}
```

Note: if `BrokerConnectionPanel` is not a default export, adjust the import to the named form it uses. Verify with `grep -n "export" frontend/src/components/settings/BrokerConnectionPanel.jsx` before writing the import line.

- [x] **Step 2: Verify it builds**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [x] **Step 3: Commit**

```bash
git add frontend/src/pages/SettingsScreen.jsx
git commit -m "feat: thermostat Settings screen (broker, mode, notifications)"
```

---

### Task 13: Rewire App routing + delete old frontend

**Files:**
- Modify: `frontend/src/App.jsx`
- Delete: old pages + orphaned components (see File Structure).

**Interfaces:**
- Consumes: `Home` (Task 10), `Coins` (Task 11), `SettingsScreen` (Task 12).
- Produces: 3-route HashRouter SPA (`#/` Home, `#/coins` Coins, `#/settings` Settings) with a bottom nav (Home / Coins / Settings, per spec §4).

- [x] **Step 1: Replace `frontend/src/App.jsx`**

```jsx
import { HashRouter, Routes, Route, NavLink } from 'react-router-dom'
import { cn } from './lib/utils.js'
import Home from './pages/Home.jsx'
import Coins from './pages/Coins.jsx'
import SettingsScreen from './pages/SettingsScreen.jsx'

function BottomNav() {
  const link = ({ isActive }) =>
    cn('flex-1 rounded-md px-3 py-2 text-center text-sm font-medium text-muted-foreground',
       isActive && 'bg-accent text-foreground')
  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 mx-auto flex max-w-md items-center gap-1 border-t border-border bg-background/90 p-2 backdrop-blur">
      <NavLink to="/" end className={link}>Home</NavLink>
      <NavLink to="/coins" className={link}>Coins</NavLink>
      <NavLink to="/settings" className={link}>Settings</NavLink>
    </nav>
  )
}

export default function App() {
  return (
    <HashRouter>
      <div className="pb-16">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/coins" element={<Coins />} />
          <Route path="/settings" element={<SettingsScreen />} />
          <Route path="*" element={<Home />} />
        </Routes>
      </div>
      <BottomNav />
    </HashRouter>
  )
}
```

- [x] **Step 2: Delete the superseded files**

```bash
git rm frontend/src/pages/MissionControl.jsx frontend/src/pages/CoinDetail.jsx frontend/src/pages/Settings.jsx
git rm frontend/src/components/CoinCard.jsx frontend/src/components/CoinsGrid.jsx \
  frontend/src/components/LiveJournal.jsx frontend/src/components/RebalancePanel.jsx \
  frontend/src/components/RebalanceStrip.jsx frontend/src/components/StatusStrip.jsx \
  frontend/src/components/AddCoinDialog.jsx frontend/src/components/AdvisorNotes.jsx \
  frontend/src/components/MiniChart.jsx frontend/src/components/useLivePrice.js
git rm -r frontend/src/components/detail
git rm frontend/src/components/settings/RiskDialPanel.jsx \
  frontend/src/components/settings/TuningJournalPanel.jsx \
  frontend/src/components/settings/DataSourcePanel.jsx \
  frontend/src/components/settings/AdvancedControls.jsx
```

- [x] **Step 3: Verify build is clean (no dangling imports)**

Run: `cd frontend && npm run build`
Expected: build succeeds with no "failed to resolve import" errors. If any deleted component is still imported somewhere, remove that import. Also run `npm run test` — Vitest must pass (only `format`, `derive`, `cache` suites remain; delete any test that imported a removed component).

- [x] **Step 4: Rebuild container + commit**

```bash
docker compose build swingbot && docker compose up -d swingbot
git add -A frontend/src
git commit -m "feat: 3-screen thermostat SPA; delete cockpit UI (old pages + panels)"
```

---

## Phase 5 — API cleanup (remove the tuning surface)

### Task 14: Remove advisor, rebalance-write, researched, risk-dial endpoints + dead modules

**Files:**
- Modify: `src/swingbot/web.py`, `src/swingbot/webmain.py`, `src/swingbot/supervisor.py`
- Delete: `src/swingbot/advisor/` (package), `src/swingbot/presets.py`
- Test: `tests/test_api_cleanup.py`; delete `tests/test_advisor_*.py`, `tests/test_presets.py`; adapt any test asserting removed routes.

**Interfaces:**
- Produces: the removed routes return 404. Backend rebalance logic stays intact and auto-runs in `tick_all` (only the manual controls/endpoints go). `create_app` no longer takes `advisor_journal`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_api_cleanup.py
from fastapi.testclient import TestClient

from swingbot.profiles import ProfileStore
from swingbot.web import create_app


class _Ctl:
    def status(self):
        return {}


def _client(tmp_path):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    return TestClient(create_app(controller=_Ctl(), profiles=profiles, creds=None, token=""))


def test_removed_routes_are_gone(tmp_path):
    c = _client(tmp_path)
    for path in ["/api/advisor/notes", "/api/advisor/journal", "/api/risk-dial",
                 "/api/strategies/researched", "/api/rebalance/run",
                 "/api/rebalance/targets", "/api/rebalance/settings"]:
        assert c.get(path).status_code == 404, path


def test_thermostat_routes_still_present(tmp_path):
    c = _client(tmp_path)
    assert c.get("/api/risk-level").status_code == 200
    assert c.get("/api/coins").status_code == 200
    assert c.get("/api/portfolio/pnl").status_code == 200
```

- [x] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_api_cleanup.py -q`
Expected: FAIL (removed routes still return 200 / advisor_journal path exists)

- [x] **Step 3: Implement the removals**

In `src/swingbot/web.py`:
- Delete the endpoints: `/api/risk-dial` (GET+PUT), `/api/advisor/notes`, `/api/advisor/journal`, `/api/advisor/revert`, `/api/advisor/revert-all`, `/api/strategies/researched` (GET+POST), `/api/rebalance/settings` (POST), `/api/rebalance/targets` (POST), `/api/rebalance/run` (POST). **Keep** `GET /api/rebalance/status` and `GET /api/rebalance/settings`/`GET /api/rebalance/targets` are optional to keep; remove the POST/PUT writers per test. Remove the helper `_apply_inverse_changes` and the `_advisor_entries` closure.
- Remove `advisor_journal` from the `create_app` signature and its uses.
- Remove now-unused imports: `RESEARCHED_META`, `RESEARCHED_PRESETS`, `RiskDialBody`, `AdvisorRevertBody` model.

In `src/swingbot/webmain.py`:
- Delete `from swingbot.advisor.journal import TuningJournal`, the `advisor_journal = TuningJournal(...)` line, and the `advisor_journal=advisor_journal` kwarg in the `create_app(...)` call.

In `src/swingbot/supervisor.py`:
- Remove the `advisor`/`advisor_interval_ticks` constructor params and `self._advisor*` attributes, and delete `_maybe_run_advisor`. (The `tick_all` call site was already removed in Task 6.)

Delete the packages/modules:

```bash
git rm -r src/swingbot/advisor
git rm src/swingbot/presets.py
git rm tests/test_advisor_digest.py tests/test_advisor_journal.py \
  tests/test_advisor_schema.py tests/test_advisor_service.py tests/test_presets.py
```

Then run the full suite and fix any remaining test that imported a removed symbol or asserted a removed route (e.g. `test_profiles_meta.py` risk-dial cases, `test_web.py` researched/advisor cases) — adapt, don't delete real coverage (spec §7).

- [x] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api_cleanup.py -q`
Expected: PASS (2 passed)

- [x] **Step 5: Full gate + rebuild + commit**

```bash
.venv/bin/python -m pytest -q && .venv/bin/ruff check src/
python3 -m graphify update .
docker compose build swingbot && docker compose up -d swingbot
git add -A src/ tests/
git commit -m "chore: remove advisor/researched/manual-tuning endpoints + dead modules (thermostat cleanup)"
```

---

## Final verification (after Task 14)

- [ ] **Backend gate:** `.venv/bin/python -m pytest -q` green; `.venv/bin/ruff check src/` clean.
- [ ] **Frontend gate:** `cd frontend && npm run build` succeeds; `npm run test` passes.
- [ ] **Container:** `docker compose build swingbot && docker compose up -d swingbot`; `curl -s localhost:8000/api/risk-level` returns a level; `curl -s localhost:8000/api/coins` returns a list.
- [ ] **Live smoke (MCP/Playwright):** load `:8000` → Home shows portfolio + Start/Stop; Coins add/remove + risk radios work; Settings shows broker panel + mode. Capture `docs/thermostat-smoke.png`.
- [ ] **Update `docs/ROADMAP_STATUS.md`** NEXT ACTION → signal-research plan (spec §8 items 6–7) and mark items 1–5 shipped.

## Self-Review (checklist run against spec §8 items 1–5)

1. **Spec coverage:** §8.1 RiskProfile → Tasks 1–3. §8.2 AutoTuner → Tasks 4–7. §8.3 thermostat frontend → Tasks 9–13. §8.4 coin onboarding → Task 8. §8.5 API cleanup → Task 14. Success criteria §9: open→see P&L (Home), add coin = symbol only (Coins/Task 8), risk change one tap → next bar (Task 3 + AutoTuner reload), AutoTuner responds without input (Task 6), no params visible (Task 13/14). §8.6–8.7 (signal research/promotion) intentionally deferred to a separate parallel plan.
2. **Placeholders:** none — every code step carries full code; the one conditional (`BrokerConnectionPanel` export form) has an explicit verify step.
3. **Type consistency:** `risk_params`/`apply_risk_level` (Task 1) used identically in Tasks 3, 5, 8. `EquitySnapshotStore.pnl_window`/`drawdown` (Task 4) used in Tasks 6–7. `TuneDecision.params` (Task 5) consumed by `_apply_effective_params` (Task 6). `api.*` method names (Task 9) match the screens (Tasks 10–12). Risk keys written are the same six everywhere.
