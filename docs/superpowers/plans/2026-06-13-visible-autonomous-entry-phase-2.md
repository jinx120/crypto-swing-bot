# Visible Autonomous Entry — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist the operator's desired-running state and auto-resume the paper-trading loop on container boot, so the bot actually starts trading after a rebuild without anyone pressing Start — while a failed auto-start never prevents the web app from serving.

**Architecture:** A new `RuntimeStateStore` (SQLite, mirroring `ProfileStore`) durably persists a single `running_desired` flag. `PortfolioSupervisor` gains a `running_desired` view, a `mark_desired()` writer, a `startup_error` attribute, and an `auto_start_if_desired()` method that resumes only a *paper*, *desired*, *armed* loop and records (never raises) failures. The FastAPI lifespan calls `auto_start_if_desired()` after the poller starts and tolerates its failure. `POST /api/control/start` marks desire true only after a successful start; `POST /api/control/stop` marks desire false before stopping; `halt`/`pause`/`resume` and app shutdown never touch desire.

**Tech Stack:** Python 3.11+, `sqlite3` (`check_same_thread=False`), FastAPI/Starlette lifespan, `threading`, pytest, FastAPI `TestClient`.

**Scope:** This plan implements only spec §5 *Phase 2* (persist desire + paper-mode auto-resume) and the §3.1 start/stop/desire contract. It does **not** persist `mode` (restart always defaults to `paper` per §3.1), persist the `paused` flag, add cycle/decision telemetry, model order/fill state, persist trades, add managed profiles/proof-of-life, add the three `/api/health/*` contracts, or rebuild the dashboard. Those are Phases 3–5.

**Builds on:** `plans/2026-06-13-visible-autonomous-entry-phase-0-1.md` (locks, interruptible loop, duplicate-loop prevention, confirmed-404 broker truth, FastAPI lifespan ownership) — all of which are already merged on `master`.

**Spec basis:** `specs/2026-06-13-visible-autonomous-entry-design-reviewed.md` §3.1 (lifecycle states + auto-start rule), §5 Phase 2, success criteria 1–2.

---

## Behavioral contract (spec §3.1, restated for this phase)

Persisted to disk (survives restart): **`running_desired`** only.

Derived / in-memory each boot:
- `mode` — constructed as `paper` every boot (no live persistence in Phase 2).
- `running_actual` — a live loop thread exists (from Phase 0/1 `lifecycle_state()`).
- `paused` — in-memory (lost on restart; out of scope to persist this phase).
- `halted` — already durable via the portfolio kill switch in `state.db`.
- `startup_error` — most recent auto-start outcome, in-memory, exposed via API.

Auto-start rule (run once on lifespan startup, after the poller starts):

```text
if mode == "paper" and running_desired and at least one armed strategy exists:
    attempt supervisor.start()
    on failure: record startup_error, do NOT raise (web app still serves)
```

Desire transitions:
- `POST /api/control/start`: start the loop; **only if start succeeds**, set `running_desired=true`.
- `POST /api/control/stop`: set `running_desired=false`, **then** stop.
- `halt`, `pause`, `resume`: never change desire.
- App shutdown: stop threads, never change desire.

Default for a fresh/existing install is `running_desired=false` — installations are never silently opted in (spec §3.1, High 4). The operator opts in by pressing Start once; every subsequent rebuild auto-resumes.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/swingbot/runtime_state.py` | Durable lifecycle desire | **New.** `RuntimeStateStore` with `get_running_desired()` / `set_running_desired()`; `CREATE TABLE IF NOT EXISTS` migration |
| `src/swingbot/supervisor.py` | Lifecycle owner | Accept `runtime_state=`; add `running_desired` property, `mark_desired()`, `startup_error` attr, `auto_start_if_desired()`; extend `lifecycle_state()` with `running_desired` + `startup_error` |
| `src/swingbot/web.py` | HTTP control + lifespan | Mark desire in `start`/`stop`; add `GET /api/control/lifecycle`; call `auto_start_if_desired()` in lifespan (failure-tolerant) |
| `src/swingbot/webmain.py` | Composition root | Build `RuntimeStateStore` and inject into the supervisor |
| `tests/test_runtime_state.py` | Persistence | **New.** default/true/false round-trips across reopen |
| `tests/test_supervisor_autostart.py` | Auto-resume logic | **New.** desire/mode/armed gating + start-failure capture |
| `tests/test_web_desire.py` | Control-layer desire + lifecycle endpoint | **New.** start marks true on success only; stop marks false before stop; lifecycle GET |
| `tests/test_web_lifespan.py` | Lifespan auto-start | Add auto-start-after-poller + survives-auto-start-failure cases |
| `docs/ROADMAP_STATUS.md` | Project status | Mark Phase 2 done; set NEXT ACTION to the Phase 3 plan |

No existing production module is repurposed beyond the supervisor/web/webmain wiring above.

---

## Phase 0 Rule (per task)

1. Add the focused test. 2. Run it; confirm the documented failure against current code. 3. Make the smallest production change. 4. Run focused + regression tests. 5. Commit test and implementation together. Never commit a deliberately red test-only commit.

Regression commands (from repo root):

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run build
```

---

### Task 1: Durable runtime-state store

**Files:**
- Create: `src/swingbot/runtime_state.py`
- Test: `tests/test_runtime_state.py`

- [x] **Step 1: Write the failing tests**

Create `tests/test_runtime_state.py`:

```python
from swingbot.runtime_state import RuntimeStateStore


def test_running_desired_defaults_false(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    assert rs.get_running_desired() is False


def test_set_running_desired_true_survives_reopen(tmp_path):
    db = str(tmp_path / "rt.db")
    RuntimeStateStore(db).set_running_desired(True)
    # A second instance simulates a process/container restart on the same file.
    assert RuntimeStateStore(db).get_running_desired() is True


def test_set_running_desired_false_clears(tmp_path):
    db = str(tmp_path / "rt.db")
    rs = RuntimeStateStore(db)
    rs.set_running_desired(True)
    rs.set_running_desired(False)
    assert RuntimeStateStore(db).get_running_desired() is False
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_runtime_state.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.runtime_state'`.

- [x] **Step 3: Implement `RuntimeStateStore`**

Create `src/swingbot/runtime_state.py`:

```python
from __future__ import annotations

import sqlite3


class RuntimeStateStore:
    """SQLite-backed durable lifecycle state for the trading loop.

    Phase 2 persists exactly one fact: whether the operator wants the loop
    running across restarts (`running_desired`). The default (no row) is False,
    so existing installations are never silently opted into auto-start.
    """

    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS runtime_state (key TEXT PRIMARY KEY, value TEXT)")
        self._conn.commit()

    def get_running_desired(self) -> bool:
        row = self._conn.execute(
            "SELECT value FROM runtime_state WHERE key='running_desired'").fetchone()
        return row is not None and row[0] == "1"

    def set_running_desired(self, desired: bool) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO runtime_state (key, value) VALUES ('running_desired', ?)",
            ("1" if desired else "0",))
        self._conn.commit()
```

- [x] **Step 4: Run the tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_runtime_state.py -q
```

Expected: PASS (3 passed).

- [x] **Step 5: Commit**

```bash
git add src/swingbot/runtime_state.py tests/test_runtime_state.py
git commit -m "feat: durable runtime-state store for desired-running flag"
```

---

### Task 2: Supervisor desire view, writer, and lifecycle reporting

**Files:**
- Modify: `src/swingbot/supervisor.py` (`PortfolioSupervisor.__init__`, `lifecycle_state`)
- Test: `tests/test_supervisor_autostart.py`

- [x] **Step 1: Write the failing tests**

Create `tests/test_supervisor_autostart.py`:

```python
from swingbot.profiles import ProfileStore
from swingbot.runtime_state import RuntimeStateStore
from swingbot.supervisor import PortfolioSupervisor
from tests.test_supervisor import FakeBroker, FakeMarket, _bars, _profile


def _supervisor(tmp_path, *, broker=None, creds=None, mode="paper",
                runtime_state=None, armed=True):
    profiles = ProfileStore(str(tmp_path / "p.db"))
    if armed:
        profiles.save("btc", _profile("BTC/USD"))
        profiles.arm("btc")
    market = FakeMarket({"BTC/USD": _bars()})
    return PortfolioSupervisor(
        profiles=profiles, creds=creds,
        state_db=str(tmp_path / "s.db"), market=market,
        broker=broker if broker is not None else FakeBroker(),
        mode=mode, runtime_state=runtime_state)


def test_running_desired_reflects_store(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    sup = _supervisor(tmp_path, runtime_state=rs)
    assert sup.running_desired is False
    rs.set_running_desired(True)
    assert sup.running_desired is True


def test_running_desired_false_without_store(tmp_path):
    sup = _supervisor(tmp_path, runtime_state=None)
    assert sup.running_desired is False
    sup.mark_desired(True)  # no store: must be a harmless no-op, not a crash
    assert sup.running_desired is False


def test_mark_desired_persists_through_store(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    sup = _supervisor(tmp_path, runtime_state=rs)
    sup.mark_desired(True)
    assert rs.get_running_desired() is True
    sup.mark_desired(False)
    assert rs.get_running_desired() is False


def test_lifecycle_state_includes_desire_and_startup_error(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    rs.set_running_desired(True)
    sup = _supervisor(tmp_path, runtime_state=rs)
    state = sup.lifecycle_state()
    assert state["running_desired"] is True
    assert state["startup_error"] is None
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_autostart.py -q
```

Expected: FAIL — `PortfolioSupervisor.__init__()` rejects `runtime_state=`, and `running_desired`/`mark_desired`/the new `lifecycle_state` keys do not exist.

- [x] **Step 3: Accept `runtime_state` and add desire fields in `__init__`**

In `src/swingbot/supervisor.py`, change the constructor signature from:

```python
    def __init__(self, profiles: ProfileStore, creds, state_db: str,
                 market: MarketData | None = None, broker=None, mode: str = "paper"):
```

to:

```python
    def __init__(self, profiles: ProfileStore, creds, state_db: str,
                 market: MarketData | None = None, broker=None, mode: str = "paper",
                 runtime_state=None):
```

Then, immediately after the existing `self.mode = mode` line in `__init__`, add:

```python
        self.runtime_state = runtime_state    # durable running_desired flag (may be None)
        self.startup_error: str | None = None  # most recent auto-start outcome
```

- [x] **Step 4: Add the `running_desired` property and `mark_desired()` writer**

Add these two members immediately after `__init__` (before the `# ---- construction ----` block):

```python
    @property
    def running_desired(self) -> bool:
        """Operator wants the loop active across restarts (durable)."""
        return bool(self.runtime_state is not None
                    and self.runtime_state.get_running_desired())

    def mark_desired(self, desired: bool) -> None:
        """Persist desire. No-op when no runtime_state store is wired."""
        if self.runtime_state is not None:
            self.runtime_state.set_running_desired(desired)
```

- [x] **Step 5: Extend `lifecycle_state()` with desire + startup_error**

In `lifecycle_state()`, replace the returned dict literal:

```python
                return {
                    "mode": self.mode,
                    "running_flag": running_flag,
                    "thread_alive": thread_alive,
                    "running_actual": running_flag and thread_alive,
                    "paused": bool(self.paused),
                    "halted": halted,
                }
```

with:

```python
                return {
                    "mode": self.mode,
                    "running_flag": running_flag,
                    "thread_alive": thread_alive,
                    "running_actual": running_flag and thread_alive,
                    "running_desired": self.running_desired,
                    "paused": bool(self.paused),
                    "halted": halted,
                    "startup_error": self.startup_error,
                }
```

- [x] **Step 6: Run focused tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_autostart.py -q
```

Expected: PASS (4 passed).

- [x] **Step 7: Run supervisor regressions**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor.py tests/test_supervisor_safety.py -q
```

Expected: PASS. The Phase 0/1 safety tests assert individual `lifecycle_state()` keys, so the two new keys do not break them.

- [x] **Step 8: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor_autostart.py
git commit -m "feat: supervisor tracks durable running_desired and startup_error"
```

---

### Task 3: `auto_start_if_desired()` — paper-only, failure-tolerant resume

**Files:**
- Modify: `src/swingbot/supervisor.py` (add method after `mark_desired`)
- Test: `tests/test_supervisor_autostart.py`

- [x] **Step 1: Add the failing tests**

Append to `tests/test_supervisor_autostart.py`:

```python
def test_auto_start_resumes_desired_paper_armed_loop(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    rs.set_running_desired(True)
    sup = _supervisor(tmp_path, runtime_state=rs)
    sup._poll_seconds = lambda: 60   # keep the loop asleep after one tick
    try:
        sup.auto_start_if_desired()
        assert sup.lifecycle_state()["running_actual"] is True
        assert sup.startup_error is None
    finally:
        sup.stop()


def test_auto_start_noop_when_not_desired(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))  # default desired=False
    sup = _supervisor(tmp_path, runtime_state=rs)
    sup.auto_start_if_desired()
    assert sup.lifecycle_state()["running_actual"] is False
    assert sup.startup_error is None


def test_auto_start_skips_live_mode(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    rs.set_running_desired(True)
    sup = _supervisor(tmp_path, mode="live", runtime_state=rs)
    sup.auto_start_if_desired()
    assert sup.lifecycle_state()["running_actual"] is False


def test_auto_start_reports_no_armed_strategies(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    rs.set_running_desired(True)
    sup = _supervisor(tmp_path, runtime_state=rs, armed=False)
    sup.auto_start_if_desired()
    assert sup.lifecycle_state()["running_actual"] is False
    assert "no armed strategies" in sup.startup_error


def test_auto_start_captures_start_failure_without_raising(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    rs.set_running_desired(True)
    # No broker and no creds -> build() raises "Alpaca credentials not set".
    sup = _supervisor(tmp_path, broker=None, creds=None, runtime_state=rs)
    sup._broker = None
    sup.auto_start_if_desired()   # must not raise
    assert sup.lifecycle_state()["running_actual"] is False
    assert "credentials" in sup.startup_error
```

- [x] **Step 2: Run the new tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_autostart.py -k auto_start -q
```

Expected: FAIL — `auto_start_if_desired` does not exist.

- [x] **Step 3: Implement `auto_start_if_desired()`**

In `src/swingbot/supervisor.py`, add this method immediately after `mark_desired()`:

```python
    def auto_start_if_desired(self) -> None:
        """Resume a previously desired paper loop on application boot.

        Records `startup_error` instead of raising, so a failed auto-start never
        prevents the web app from serving. Only paper mode auto-resumes; live is
        never started automatically. Does not change `running_desired`.
        """
        self.startup_error = None
        if self.mode != "paper":
            return
        if not self.running_desired:
            return
        if not self.profiles.list_armed():
            self.startup_error = "running desired but no armed strategies to resume"
            return
        try:
            self.start()
        except Exception as e:
            self.startup_error = f"auto-start failed: {e}"
```

- [x] **Step 4: Run the auto-start tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_autostart.py -q
```

Expected: PASS (9 passed total in this file).

- [x] **Step 5: Run supervisor regressions**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor.py tests/test_supervisor_safety.py tests/test_supervisor_control.py -q
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor_autostart.py
git commit -m "feat: paper-only failure-tolerant auto-resume on boot"
```

---

### Task 4: Control endpoints set desire + lifecycle endpoint

**Files:**
- Modify: `src/swingbot/web.py` (`control_start`, `control_stop`, add `control_lifecycle`)
- Test: `tests/test_web_desire.py`

- [x] **Step 1: Write the failing tests**

Create `tests/test_web_desire.py`:

```python
from fastapi.testclient import TestClient

from swingbot.web import create_app


class DesireController:
    def __init__(self, start_error=None):
        self.calls = []
        self.desired = None
        self.start_error = start_error
        self._lifecycle = {"running_desired": False, "running_actual": False,
                           "startup_error": None}

    def status(self): return {}
    def journal(self, strategy=None): return []
    def metrics(self, strategy=None): return {}

    def start(self):
        self.calls.append("start")
        if self.start_error is not None:
            raise self.start_error

    def stop(self):
        self.calls.append("stop")

    def mark_desired(self, desired):
        self.calls.append(("mark_desired", desired))
        self.desired = desired

    def lifecycle_state(self):
        return self._lifecycle


def _client(ctrl):
    return TestClient(create_app(controller=ctrl, profiles=None, creds=None, token="t"))


def test_start_marks_desired_true_after_success():
    ctrl = DesireController()
    r = _client(ctrl).post("/api/control/start", headers={"X-Token": "t"})
    assert r.status_code == 200
    assert ctrl.desired is True
    assert ctrl.calls.index("start") < ctrl.calls.index(("mark_desired", True))


def test_failed_start_does_not_mark_desired():
    ctrl = DesireController(start_error=RuntimeError("boom"))
    r = _client(ctrl).post("/api/control/start", headers={"X-Token": "t"})
    assert r.status_code == 400
    assert ctrl.desired is None
    assert ("mark_desired", True) not in ctrl.calls


def test_stop_marks_desired_false_before_stopping():
    ctrl = DesireController()
    r = _client(ctrl).post("/api/control/stop", headers={"X-Token": "t"})
    assert r.status_code == 200
    assert ctrl.desired is False
    assert ctrl.calls.index(("mark_desired", False)) < ctrl.calls.index("stop")


def test_lifecycle_endpoint_returns_state():
    ctrl = DesireController()
    r = _client(ctrl).get("/api/control/lifecycle")
    assert r.status_code == 200
    assert r.json()["running_desired"] is False
    assert "startup_error" in r.json()
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_desire.py -q
```

Expected: FAIL — `start`/`stop` do not call `mark_desired`, and `GET /api/control/lifecycle` returns 404.

- [x] **Step 3: Mark desire in `control_start` / `control_stop`**

In `src/swingbot/web.py`, replace the existing `control_start` and `control_stop` handlers:

```python
    @app.post("/api/control/start")
    def control_start(_=Depends(require_token)):
        try:
            controller.start()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}

    @app.post("/api/control/stop")
    def control_stop(_=Depends(require_token)):
        controller.stop(); return {"ok": True}
```

with:

```python
    @app.post("/api/control/start")
    def control_start(_=Depends(require_token)):
        try:
            controller.start()
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        if hasattr(controller, "mark_desired"):
            controller.mark_desired(True)   # persist desire only after a successful start
        return {"ok": True}

    @app.post("/api/control/stop")
    def control_stop(_=Depends(require_token)):
        if hasattr(controller, "mark_desired"):
            controller.mark_desired(False)  # clear desire first, then stop
        controller.stop()
        return {"ok": True}
```

- [x] **Step 4: Add the lifecycle GET endpoint**

In `src/swingbot/web.py`, immediately after the `control_stop` handler, add:

```python
    @app.get("/api/control/lifecycle")
    def control_lifecycle():
        if hasattr(controller, "lifecycle_state"):
            return controller.lifecycle_state()
        return {}
```

- [x] **Step 5: Run focused + control regressions to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_desire.py tests/test_web_control.py -q
```

Expected: PASS. The existing `test_web_control.py` fakes lack `mark_desired`/`lifecycle_state`, so the `hasattr` guards leave those tests unchanged.

- [x] **Step 6: Commit**

```bash
git add src/swingbot/web.py tests/test_web_desire.py
git commit -m "feat: control endpoints persist desire; add lifecycle endpoint"
```

---

### Task 5: Lifespan auto-start (failure-tolerant)

**Files:**
- Modify: `src/swingbot/web.py` (the `lifespan` async context manager)
- Test: `tests/test_web_lifespan.py`

- [x] **Step 1: Add failing lifespan tests**

Append to `tests/test_web_lifespan.py`:

```python
class AutoStartController(RecordingController):
    def __init__(self, events, raise_error=None):
        super().__init__(events)
        self.raise_error = raise_error

    def auto_start_if_desired(self):
        self.events.append("controller:auto_start")
        if self.raise_error is not None:
            raise self.raise_error


def test_lifespan_auto_starts_after_poller():
    events = []
    app = create_app(
        AutoStartController(events), profiles=None, creds=None, token="t",
        poller=RecordingPoller(events))
    with TestClient(app):
        assert events[:2] == ["poller:start", "controller:auto_start"]


def test_lifespan_survives_auto_start_failure():
    events = []
    app = create_app(
        AutoStartController(events, RuntimeError("auto boom")),
        profiles=None, creds=None, token="t", poller=RecordingPoller(events))
    # The web app must still boot and serve even though auto-start raised.
    with TestClient(app) as client:
        assert client.get("/api/state").status_code == 200
    assert "controller:auto_start" in events
    assert events[-1] == "poller:stop"
```

- [x] **Step 2: Run the tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_lifespan.py -q
```

Expected: FAIL — the lifespan never calls `auto_start_if_desired`, so `controller:auto_start` is absent.

- [x] **Step 3: Call `auto_start_if_desired()` in the lifespan**

In `src/swingbot/web.py`, replace the existing lifespan body:

```python
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if poller is not None:
            poller.start()
        try:
            yield
        finally:
            try:
                if controller is not None and hasattr(controller, "stop"):
                    controller.stop()
            finally:
                if poller is not None:
                    poller.stop()
```

with:

```python
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if poller is not None:
            poller.start()
        if controller is not None and hasattr(controller, "auto_start_if_desired"):
            try:
                controller.auto_start_if_desired()
            except Exception as e:   # auto-start must never prevent the app from serving
                print(f"[lifespan] auto-start error: {e}")
        try:
            yield
        finally:
            try:
                if controller is not None and hasattr(controller, "stop"):
                    controller.stop()
            finally:
                if poller is not None:
                    poller.stop()
```

- [x] **Step 4: Run lifespan + web regressions to verify they pass**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_web_lifespan.py \
  tests/test_web_read.py \
  tests/test_web_control.py \
  tests/test_web_desire.py -q
```

Expected: PASS. The pre-existing `RecordingController` in `test_web_lifespan.py` has no `auto_start_if_desired`, so the three original lifespan tests still see `events == ["poller:start"]` on entry.

- [x] **Step 5: Commit**

```bash
git add src/swingbot/web.py tests/test_web_lifespan.py
git commit -m "feat: auto-resume desired paper loop in FastAPI lifespan"
```

---

### Task 6: Wire `RuntimeStateStore` into composition root + acceptance

**Files:**
- Modify: `src/swingbot/webmain.py`
- Modify after verification: `docs/ROADMAP_STATUS.md`

- [x] **Step 1: Inject the runtime-state store**

In `src/swingbot/webmain.py`, add this import after the existing `from swingbot.profiles import ProfileStore` line:

```python
from swingbot.runtime_state import RuntimeStateStore
```

Then replace the supervisor construction:

```python
    supervisor = PortfolioSupervisor(
        profiles=profiles, creds=creds,
        state_db=os.path.join(DATA_DIR, "swingbot.db"), market=market)
```

with:

```python
    runtime_state = RuntimeStateStore(os.path.join(DATA_DIR, "swingbot.db"))
    supervisor = PortfolioSupervisor(
        profiles=profiles, creds=creds,
        state_db=os.path.join(DATA_DIR, "swingbot.db"), market=market,
        runtime_state=runtime_state)
```

No change to the `create_app(...)` call is required: the web layer reaches desire/auto-start/lifecycle through the `controller` it already receives.

- [x] **Step 2: Verify imports compose**

Run:

```bash
.venv/bin/python -c "import swingbot.webmain; print('ok')"
```

Expected: prints `ok` (the module imports and wires without error).

- [x] **Step 3: Run the full Python suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: PASS (Phase 0/1 baseline was `394 passed, 6 skipped`; this phase adds new passing tests — expect ~`410 passed, 6 skipped`). If an unrelated pre-existing failure appears, confirm it against the base commit before recording it as pre-existing.

- [x] **Step 4: Build the frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds (no frontend changes this phase; this confirms no regression).

- [x] **Step 5: Rebuild and restart the container**

Run:

```bash
docker compose build swingbot
docker compose up -d swingbot
docker compose ps
docker compose logs --tail=60 swingbot
```

Expected: container running; clean lifespan startup; no duplicate-loop / leaked-thread / poller errors. With a fresh install `running_desired` defaults false, so the loop does **not** auto-start yet (correct: no silent opt-in).

- [x] **Step 6: Acceptance — opt in once, then prove auto-resume**

Replace `TOKEN` with the value printed in the logs (`[swingbot-web] token: ...`), and ensure at least one strategy is armed.

```bash
# 1. Opt in: start the loop (persists running_desired=true).
curl -s -X POST localhost:8000/api/control/start -H "X-Token: TOKEN"
# 2. Confirm desire + actual running.
curl -s localhost:8000/api/control/lifecycle
#    expect: "running_desired": true, "running_actual": true, "startup_error": null
# 3. Rebuild + restart WITHOUT pressing Start.
docker compose build swingbot && docker compose up -d swingbot
sleep 5
# 4. Confirm the loop auto-resumed on boot.
curl -s localhost:8000/api/control/lifecycle
#    expect: "running_desired": true, "running_actual": true
```

Then prove explicit stop survives restart:

```bash
curl -s -X POST localhost:8000/api/control/stop -H "X-Token: TOKEN"
docker compose restart swingbot
sleep 5
curl -s localhost:8000/api/control/lifecycle
#    expect: "running_desired": false, "running_actual": false
```

Expected: step 4 shows the loop running with no button press (success criterion 1); the final check shows an explicit stop stays stopped across restart (success criterion 2). If `startup_error` is non-null at step 4, read it — it is the captured auto-start failure, and the web API is still served (success criterion: app available when auto-start fails).

- [x] **Step 7: Update the roadmap**

Edit `docs/ROADMAP_STATUS.md`:
- Mark **Visible Autonomous Entry — Phase 2** complete (persisted desire + paper auto-resume), referencing this plan and the acceptance evidence from Step 6.
- Set **NEXT ACTION** to: *write the Phase 3 plan* — durable cycle/decision telemetry, order/pending/fill state with broker-confirmed positions, persistent trades, and the three `/api/health/*` contracts (spec §5 Phase 3). Spec basis: `specs/2026-06-13-visible-autonomous-entry-design-reviewed.md`.

- [x] **Step 8: Commit**

```bash
git add src/swingbot/webmain.py docs/ROADMAP_STATUS.md
git commit -m "feat: wire runtime-state store; mark autonomous-entry phase 2 complete"
```

---

## Self-Review Checklist

Before execution handoff, confirm:

- [x] `running_desired` is the only fact persisted to disk; it defaults to false (no silent opt-in).
- [x] `mode` is constructed as `paper` every boot; live is never auto-started.
- [x] `POST /api/control/start` sets desire true **only** after `controller.start()` succeeds.
- [x] `POST /api/control/stop` sets desire false **before** stopping.
- [x] `halt`, `pause`, `resume`, and app shutdown never call `mark_desired`.
- [x] `auto_start_if_desired()` records `startup_error` and never raises.
- [x] The lifespan tolerates an `auto_start_if_desired()` exception and still serves requests.
- [x] `auto_start_if_desired()` runs after `poller.start()`.
- [x] `lifecycle_state()` exposes `running_desired` and `startup_error`.
- [x] `hasattr` guards keep all pre-existing web/lifespan fakes green.
- [x] No telemetry, order/fill, trade-persistence, managed-profile, health-contract, or dashboard behavior is changed (those are Phases 3–5).
- [x] No deliberately failing commit is created.

---

## Spec Coverage Map (§5 Phase 2)

| Spec Phase 2 item | Task |
|---|---|
| 1. Dedicated runtime-state record / schema migration | Task 1 (+ wiring Task 6) |
| 2. Update start/stop semantics per §3.1 | Tasks 2, 3, 4 |
| 3. Lifespan auto-start with visible `startup_error` | Tasks 3, 5 (+ `lifecycle` endpoint Task 4) |
| 4. Keep web API available when auto-start fails | Tasks 3, 5 (failure-tolerant) |
| Exit: resume desired paper loop after restart | Task 6 Step 6 |
| Exit: explicit stop survives restart | Task 6 Step 6 |
| Exit: halted/paused loops still resume to manage positions | Tasks 3, 5 (desire untouched by halt/pause; halt durable via kill switch) |

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-13-visible-autonomous-entry-phase-2.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration. REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`.

**2. Inline Execution** — execute tasks in this session with checkpoints. REQUIRED SUB-SKILL: `superpowers:executing-plans`.

Per the project's standing authorization, inline end-to-end execution (committing per task, Docker rebuild per the standing rule) is pre-approved.
