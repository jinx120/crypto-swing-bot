# Visible Autonomous Entry — Phase 2.1 Lifecycle Failure-Path Hardening Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the operator-facing lifecycle commands (`request_start`, `request_stop`, `stop`, `lifecycle_state`) report **truthful** outcomes when durable-state persistence fails, a runtime-state read fails, or a loop thread does not stop within the join timeout — without weakening the concurrency serialization shipped in `2f13bda`.

**Architecture:** Introduce a small typed lifecycle-exception hierarchy (`LifecycleError`, `DesirePersistError`) carrying structured failure attributes. `stop()` returns a `bool` (`True` = fully stopped, `False` = thread still alive after join) instead of silently returning, while still retaining the live thread reference so duplicate starts stay blocked. `request_start()` rolls back a loop it just started if desire-persistence fails; `request_stop()` always attempts to stop even when desire-clearing fails, and surfaces both errors. `lifecycle_state()` tolerates an unreadable runtime store (reports `running_desired=null` plus an error field) and reports `running_actual` as *thread-alive* per the reviewed contract. The web endpoints map these incomplete lifecycle operations to non-`{"ok": true}` HTTP 500 responses with actionable detail.

**Tech Stack:** Python 3.11+, `threading` (`RLock`, `Event`, `Thread`), `sqlite3` (`check_same_thread=False`), FastAPI/Starlette + `TestClient`, pytest.

**Scope:** This plan implements **only** the four findings in `docs/superpowers/plans/2026-06-14-phase2-lifecycle-code-review-handoff.md` against the lifecycle surface added in Phase 2. It does **not** add cycle/decision telemetry, order/fill state, durable trades, the `/api/health/*` contracts, managed profiles, or any dashboard change — those remain Phase 3+. It does **not** change trading-strategy behavior, remove the lifecycle/state lock ordering, persist `mode`, or alter the default `running_desired=false`.

**Builds on:** `docs/superpowers/plans/2026-06-13-visible-autonomous-entry-phase-2.md` (durable `RuntimeStateStore`, `request_start`/`request_stop`, `auto_start_if_desired`, `lifecycle_state`, `GET /api/control/lifecycle`) — merged on `master`, review corrections at `2f13bda`.

**Review basis:** `docs/superpowers/plans/2026-06-14-phase2-lifecycle-code-review-handoff.md` (Findings 1–4, suggested implementation order, scope guardrails). **Reviewed head:** `2f13bda35d5730ddc37fdc1584335d6228c4b44f`.

**Spec basis:** `docs/superpowers/specs/2026-06-13-visible-autonomous-entry-design-reviewed.md` §3.1 (lifecycle states table — `running_actual` = "loop thread is alive"; `startup_error` "visible in API/UI").

---

## Why this precedes the Phase 3 plan

Phase 3 adds `/api/health/trading`, which the spec (§3.3) defines in terms of *desired vs. actual* loop state: "A desired-but-not-running loop is immediately unhealthy." That health contract is only meaningful if `running_actual` and `running_desired` are reported truthfully. Today:

- `running_actual` is computed as `running_flag and thread_alive`, so a hung loop (flag cleared, thread alive) reports **not running** — which would make `/api/health/trading` declare a stuck bot *healthy/inactive*.
- A runtime-state read failure makes the whole `lifecycle_state()` (and thus any future health endpoint built on it) raise instead of reporting the failure.
- Start/Stop can report success while the true state diverges from what the operator asked for.

Fixing the lifecycle truth layer **now** means Phase 3's health/telemetry work builds on a state surface that already cannot lie. This is hardening of completed Phase 2 work, executed before the Phase 3 plan is written.

---

## Design decisions (locked — do not re-litigate during execution)

1. **Exceptions, not result objects.** Failure paths raise typed exceptions rather than returning a status object. Rationale: `request_start`/`request_stop` already contract "no exception = success," and the web layer already maps exceptions to HTTP errors. A result object can be silently ignored by a caller — which is the exact bug class (`{"ok": true}` while the thread is alive) we are removing. An exception cannot be silently dropped.

2. **`stop()` returns `bool`, never raises for timeout.** `stop()` is called from many internal paths (`set_mode`, `request_stop`, internal). Returning `True`/`False` is backward-compatible (existing callers that ignore the return keep working) and lets the explicit-operator wrappers decide whether a timeout is an error. The live thread reference is **retained** on timeout (already the case), so duplicate-start prevention is preserved.

3. **Rollback only what this call started.** `request_start()` captures `was_running = self._running` *before* `start()`. It rolls the loop back on persist failure **only if it actually started the loop** (`not was_running`) — pressing Start while already running must never stop a loop the operator did not ask to stop.

4. **`request_stop()` always attempts stop.** Desire is still cleared *first* (restart-safety intent preserved), but a persistence failure no longer skips the stop — both failures are collected and raised together.

5. **`running_actual` = thread-alive.** Per spec §3.1. `running_flag` (the internal `_running` bool) is kept as a *separate* field for diagnostics.

6. **Unreadable desire is `null`, not `false`.** `lifecycle_state()` reports `running_desired: None` plus `running_desired_error: "<message>"` when the store raises, so an unreadable store is never silently rendered as "operator does not want it running."

7. **HTTP status mapping.** Pre-condition/duplicate `RuntimeError` from `start()` → **400** (unchanged, preserves existing `test_failed_request_start_surfaces_400`). New `LifecycleError`/`DesirePersistError` (partial/incomplete lifecycle outcomes) → **500** with the exception message as `detail`. The lifecycle GET never raises and stays **200**.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/swingbot/supervisor.py` | Lifecycle owner | **Modify.** Add `LifecycleError` + `DesirePersistError` classes; make `stop()` return `bool`; rewrite `request_start()` (rollback) and `request_stop()` (always-stop + combined errors); make `lifecycle_state()` tolerate runtime-state read failure and report `running_actual=thread_alive` + `running_flag` + `running_desired_error`; update `set_mode()` to consume `stop()`'s bool. |
| `src/swingbot/web.py` | HTTP control surface | **Modify.** `POST /api/control/start` and `/api/control/stop` map `LifecycleError` → HTTP 500 with detail; `start` keeps plain `RuntimeError` → 400. Import the exception types. |
| `tests/test_supervisor_safety.py` | Lifecycle invariants | **Modify.** Update the join-timeout test to the reviewed `running_actual=true` contract; add a `stop()`-returns-False-on-timeout assertion. |
| `tests/test_supervisor_autostart.py` | Request-operation behavior | **Modify.** Add Start-rollback-on-persist-failure, Stop-always-stops-on-persist-failure, combined-failure, and unreadable-desire reporting tests. |
| `tests/test_web_desire.py` | Control-layer HTTP truth | **Modify.** Add endpoint cases: Start persist-failure → 500, Stop timeout/persist-failure → 500 (not `{"ok": true}`), lifecycle GET exposes `startup_error` + `running_desired=null` when the store is unreadable. |
| `docs/ROADMAP_STATUS.md` | Project status | **Modify.** Record Phase 2.1 as the active NEXT ACTION ahead of the Phase 3 plan; update on completion. |

No new module is introduced; the exception types live beside the supervisor that raises them.

---

## Phase 0 Rule (per task)

1. Add/adjust the focused test. 2. Run it; confirm the documented red state against current code. 3. Make the smallest production change. 4. Run focused + full regression. 5. Commit test and implementation together. Never commit a deliberately red test-only commit.

**Standing docker policy (project CLAUDE.md):** after the final code task, rebuild + restart the container unconditionally:
```bash
docker compose build swingbot && docker compose up -d swingbot
```

Regression commands (from repo root):
```bash
.venv/bin/python -m pytest -q
ruff check src tests
cd frontend && npm run build
```

Targeted lifecycle suite (per the handoff "Verification Required After Fixes"):
```bash
.venv/bin/python -m pytest -q \
  tests/test_runtime_state.py \
  tests/test_supervisor_autostart.py \
  tests/test_supervisor_safety.py \
  tests/test_web_desire.py \
  tests/test_web_lifespan.py
```

---

### Task 1: Lifecycle exception types + `stop()` returns a truthful bool

Implements handoff **Finding 2 (stop truthfulness)** and the suggested-order step 1 ("dedicated exceptions") and step 2's prerequisite. This task adds the vocabulary the later tasks raise/consume and makes a timed-out stop *distinguishable* from a completed stop, while keeping the retained-thread invariant.

**Files:**
- Modify: `src/swingbot/supervisor.py` (new exception classes near top; `stop()`; `set_mode()`)
- Test: `tests/test_supervisor_safety.py`

- [ ] **Step 1: Write/adjust the failing tests**

In `tests/test_supervisor_safety.py`, add an import at the top alongside the existing supervisor import:

```python
from swingbot.supervisor import LifecycleError
```

Replace the body of `test_stop_retains_live_thread_after_join_timeout` (currently asserts `running_actual is False` while the thread is alive) with the reviewed contract, and assert `stop()`'s new return value:

```python
def test_stop_retains_live_thread_after_join_timeout(tmp_path):
    sup = _running_supervisor_with_stuck_tick(tmp_path)
    sup._join_timeout = 0.05
    try:
        stopped = sup.stop()
        # A timed-out stop is distinguishable from a completed stop.
        assert stopped is False
        state = sup.lifecycle_state()
        assert state["thread_alive"] is True
        # Reviewed contract (spec 3.1): running_actual == loop thread is alive.
        assert state["running_actual"] is True
        # The internal flag is cleared and reported separately.
        assert state["running_flag"] is False
        # A later Start stays blocked while that thread is alive.
        with pytest.raises(RuntimeError, match="still alive"):
            sup.start()
    finally:
        _release_stuck_tick(sup)
```

> **Engineer note:** This test reuses the file's existing stuck-tick helper and `_join_timeout` override (see the current `test_stop_retains_live_thread_after_join_timeout` and `test_mode_does_not_change_when_stop_times_out` for the exact fixture names — `_running_supervisor_with_stuck_tick` / `_release_stuck_tick` are illustrative; use whatever the file already defines to install a blocking tick). Do **not** introduce a new fixture if one exists; only change the assertions and add the `stopped`/`running_flag` checks. Ensure `import pytest` is present (it already is for the existing `pytest.raises` calls).

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
.venv/bin/python -m pytest tests/test_supervisor_safety.py::test_stop_retains_live_thread_after_join_timeout -q
```
Expected: FAIL — `stop()` currently returns `None` (so `stopped is False` fails), `running_actual` is currently `False`, and `running_flag` is not yet a key.

- [ ] **Step 3: Add the exception types**

In `src/swingbot/supervisor.py`, immediately after the imports (before `_CANON`), add:

```python
class LifecycleError(RuntimeError):
    """An explicit operator lifecycle command (start/stop) did not fully succeed.

    Carries structured attributes so the web layer can report a truthful,
    actionable outcome instead of a bare success. `persist_error` is the
    underlying desire-persistence exception (or None); `stop_timed_out` is True
    when the loop thread was still alive after the join timeout; `rolled_back`
    indicates whether a partially-started loop was successfully stopped again
    (None when not applicable).
    """

    def __init__(self, message: str, *, persist_error: Exception | None = None,
                 stop_timed_out: bool = False, rolled_back: bool | None = None):
        super().__init__(message)
        self.persist_error = persist_error
        self.stop_timed_out = stop_timed_out
        self.rolled_back = rolled_back


class DesirePersistError(LifecycleError):
    """Persisting the durable `running_desired` flag failed during an explicit
    start/stop. Subclass so callers may catch it specifically while still
    matching `LifecycleError`."""
```

- [ ] **Step 4: Make `stop()` return a bool**

Replace `stop()` in `src/swingbot/supervisor.py` with (note the `-> bool` and the returns; the thread reference is still only cleared when the thread is actually gone):

```python
    def stop(self) -> bool:
        # Lifecycle lock remains held across join so concurrent start/set_mode
        # cannot race this transition. Do not take the state lock here: a hung
        # tick may hold it, and stop must still signal and time out.
        # Returns True if the loop is fully stopped (no live thread), False if
        # the thread was still alive after the join timeout. On False the thread
        # reference is retained so a second Start stays blocked.
        with self._lifecycle_lock:
            self._running = False
            self._stop_event.set()
            thread = self._thread
            if thread is None:
                return True
            if thread is threading.current_thread():
                return True
            thread.join(timeout=self._join_timeout)
            if thread.is_alive():
                return False
            if self._thread is thread:
                self._thread = None
            return True
```

- [ ] **Step 5: Consume the bool in `set_mode()`**

In `set_mode()`, replace the post-stop liveness re-check with the returned bool (semantically identical, but uses the single source of truth):

```python
            if not self.stop():
                return (False, "previous loop thread still alive; mode unchanged")
```

(Delete the now-redundant `if self._thread is not None and self._thread.is_alive(): return (False, ...)` block that immediately followed the old `self.stop()` call.)

- [ ] **Step 6: Report `running_actual` and `running_flag` per contract**

In `lifecycle_state()`, change the returned dict so `running_actual` is thread-alive and `running_flag` is reported separately (the `running_desired` tolerance is added in Task 4; leave that line as-is for now):

```python
                    "running_flag": running_flag,
                    "thread_alive": thread_alive,
                    "running_actual": thread_alive,
```

- [ ] **Step 7: Run focused + regression**

Run:
```bash
.venv/bin/python -m pytest tests/test_supervisor_safety.py tests/test_supervisor_autostart.py -q
.venv/bin/python -m pytest -q
```
Expected: the adjusted safety test PASSES; full suite PASSES. If any other test asserted the old `running_actual = running_flag and thread_alive` semantics in a thread-alive-but-flag-false case, update it to the reviewed contract (search: `running_actual`). The autostart tests that assert `running_actual is False` are all thread-not-alive cases and remain valid.

- [ ] **Step 8: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor_safety.py
git commit -m "feat(lifecycle): typed lifecycle errors; stop() returns truthful bool; running_actual=thread-alive"
```

---

### Task 2: `request_start()` rolls back a started loop when desire-persistence fails

Implements handoff **Finding 1**.

**Files:**
- Modify: `src/swingbot/supervisor.py` (`request_start()`)
- Test: `tests/test_supervisor_autostart.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_supervisor_autostart.py`, add (reuse the existing `RecordingRuntimeState` / `_supervisor` helpers in the file; extend `RecordingRuntimeState` with a settable failure if it lacks one):

```python
class _RaiseOnSetRuntimeState:
    """Runtime store whose desire-read works but desire-write raises."""
    def __init__(self):
        self._desired = False
    def get_running_desired(self):
        return self._desired
    def set_running_desired(self, desired):
        raise RuntimeError("disk full")


def test_request_start_rolls_back_when_persist_fails(tmp_path):
    from swingbot.supervisor import DesirePersistError
    sup = _supervisor(tmp_path, runtime_state=_RaiseOnSetRuntimeState())
    with pytest.raises(DesirePersistError) as exc:
        sup.request_start()
    # The newly started loop must be rolled back.
    state = sup.lifecycle_state()
    assert state["running_actual"] is False
    assert state["thread_alive"] is False
    assert exc.value.rolled_back is True
    assert exc.value.persist_error is not None


def test_request_start_does_not_clear_startup_error_on_persist_failure(tmp_path):
    sup = _supervisor(tmp_path, runtime_state=_RaiseOnSetRuntimeState())
    sup.startup_error = "auto-start failed: earlier boom"
    with pytest.raises(Exception):
        sup.request_start()
    # A failed Start must not clear a stale startup_error.
    assert sup.startup_error == "auto-start failed: earlier boom"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
.venv/bin/python -m pytest tests/test_supervisor_autostart.py -k "rolls_back or does_not_clear_startup" -q
```
Expected: FAIL — current `request_start()` leaves `running_actual` true (loop started, never rolled back) and raises a bare `RuntimeError`, not `DesirePersistError`.

- [ ] **Step 3: Implement rollback**

Replace `request_start()` in `src/swingbot/supervisor.py`:

```python
    def request_start(self) -> None:
        """Handle an explicit operator Start as one serialized lifecycle operation.

        Start and desire-persistence are atomic under the lifecycle lock. Desire
        is marked only after start() succeeds. If persisting desire fails AND this
        call is what started the loop, roll the loop back so the operator is never
        told Start failed while a live thread keeps trading. A stale startup_error
        is cleared only on full success.
        """
        with self._lifecycle_lock:
            was_running = self._running
            self.start()  # precondition failures (e.g. duplicate thread) propagate as RuntimeError
            try:
                self.mark_desired(True)
            except Exception as persist_err:
                rolled_back: bool | None = None
                if not was_running:
                    rolled_back = self.stop()  # only stop a loop THIS call started
                raise DesirePersistError(
                    "started loop but failed to persist running_desired=true: "
                    f"{persist_err}; "
                    + ("loop rolled back" if rolled_back
                       else "ROLLBACK STOP TIMED OUT — loop thread still alive"
                       if rolled_back is False
                       else "loop was already running before this request; left running"),
                    persist_error=persist_err,
                    stop_timed_out=(rolled_back is False),
                    rolled_back=rolled_back) from persist_err
            self.startup_error = None
```

- [ ] **Step 4: Run focused + regression**

Run:
```bash
.venv/bin/python -m pytest tests/test_supervisor_autostart.py -q
.venv/bin/python -m pytest -q
```
Expected: PASS. The existing `test_request_start_marks_desire_after_success` (asserts `calls == ["start", ("mark_desired", True)]`) still passes — `was_running` reads the in-memory `_running` bool and records no store call.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor_autostart.py
git commit -m "fix(lifecycle): roll back a started loop when Start desire-persistence fails"
```

---

### Task 3: `request_stop()` always stops and surfaces both failures

Implements handoff **Finding 4** (skip-stop-on-persist-failure) and the stop-timeout half of **Finding 2**.

**Files:**
- Modify: `src/swingbot/supervisor.py` (`request_stop()`)
- Test: `tests/test_supervisor_autostart.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_supervisor_autostart.py`, add:

```python
def test_request_stop_still_stops_when_clearing_desire_fails(tmp_path):
    from swingbot.supervisor import LifecycleError
    sup = _supervisor(tmp_path, runtime_state=_RaiseOnSetRuntimeState())
    sup.start()
    assert sup.lifecycle_state()["thread_alive"] is True
    with pytest.raises(LifecycleError) as exc:
        sup.request_stop()
    # Stop must have been attempted despite the persistence failure.
    assert sup.lifecycle_state()["thread_alive"] is False
    assert exc.value.persist_error is not None
    assert "auto-resume" in str(exc.value)


def test_request_stop_succeeds_when_everything_works(tmp_path):
    rs = RuntimeStateStore(str(tmp_path / "rt.db"))
    sup = _supervisor(tmp_path, runtime_state=rs)
    sup.start()
    sup.request_stop()  # no exception
    assert sup.lifecycle_state()["thread_alive"] is False
    assert rs.get_running_desired() is False
```

> **Engineer note:** ensure `from swingbot.runtime_state import RuntimeStateStore` is imported at the top of the test file (it already is, per the existing autostart tests).

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
.venv/bin/python -m pytest tests/test_supervisor_autostart.py -k "request_stop_still_stops or request_stop_succeeds" -q
```
Expected: the `still_stops` test FAILS — current `request_stop()` calls `mark_desired(False)` first, which raises, so `stop()` never runs and the thread stays alive; it also raises a bare `RuntimeError`, not `LifecycleError`.

- [ ] **Step 3: Implement always-stop with combined errors**

Replace `request_stop()` in `src/swingbot/supervisor.py`:

```python
    def request_stop(self) -> None:
        """Handle an explicit operator Stop as one serialized lifecycle operation.

        Desire is cleared first (so a restart cannot auto-resume), but the current
        process is ALWAYS asked to stop even if clearing desire fails — an explicit
        Stop must never leave the loop trading. Persistence and stop failures are
        both surfaced; success raises nothing.
        """
        with self._lifecycle_lock:
            persist_err: Exception | None = None
            try:
                self.mark_desired(False)
            except Exception as e:
                persist_err = e
            stopped = self.stop()  # always attempt, even if desire-clear failed
            problems: list[str] = []
            if persist_err is not None:
                problems.append(
                    "failed to clear running_desired (restart may auto-resume): "
                    f"{persist_err}")
            if not stopped:
                problems.append("stop timed out; loop thread still alive")
            if problems:
                raise LifecycleError(
                    "; ".join(problems),
                    persist_error=persist_err,
                    stop_timed_out=not stopped) from persist_err
```

- [ ] **Step 4: Run focused + regression**

Run:
```bash
.venv/bin/python -m pytest tests/test_supervisor_autostart.py -q
.venv/bin/python -m pytest -q
```
Expected: PASS. Existing `test_request_stop_clears_desire_before_stop` (asserts `calls == [("mark_desired", False), "stop"]`) still passes — order is unchanged on the success path.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor_autostart.py
git commit -m "fix(lifecycle): explicit Stop always stops and surfaces both persist+stop failures"
```

---

### Task 4: `lifecycle_state()` tolerates an unreadable runtime store

Implements handoff **Finding 3**.

**Files:**
- Modify: `src/swingbot/supervisor.py` (`lifecycle_state()`)
- Test: `tests/test_supervisor_autostart.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_supervisor_autostart.py`, add:

```python
class _RaiseOnGetRuntimeState:
    """Runtime store whose desire-read raises (write is a harmless no-op)."""
    def get_running_desired(self):
        raise RuntimeError("runtime-state read failed")
    def set_running_desired(self, desired):
        pass


def test_lifecycle_state_tolerates_unreadable_desire(tmp_path):
    sup = _supervisor(tmp_path, runtime_state=_RaiseOnGetRuntimeState())
    # auto_start_if_desired already captures the read failure into startup_error
    sup.auto_start_if_desired()  # must not raise
    state = sup.lifecycle_state()  # must not raise
    assert state["running_desired"] is None
    assert "runtime-state read failed" in state["running_desired_error"]
    # The captured auto-start failure remains visible.
    assert state["startup_error"] is not None
    assert "runtime-state read failed" in state["startup_error"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
.venv/bin/python -m pytest tests/test_supervisor_autostart.py::test_lifecycle_state_tolerates_unreadable_desire -q
```
Expected: FAIL — `lifecycle_state()` reads `self.running_desired`, which calls `get_running_desired()` and raises, so the call itself errors out.

- [ ] **Step 3: Implement tolerance**

In `src/swingbot/supervisor.py`, replace the `lifecycle_state()` return block so the desire read is guarded (keep the `running_actual`/`running_flag` changes from Task 1):

```python
    def lifecycle_state(self) -> dict:
        with self._lifecycle_lock:
            thread_alive = bool(self._thread is not None and self._thread.is_alive())
            running_flag = bool(self._running)
            try:
                running_desired: bool | None = self.running_desired
                running_desired_error: str | None = None
            except Exception as e:
                # An unreadable store must not break the lifecycle endpoint, and
                # unreadable desire is reported as null (not a silent false).
                running_desired = None
                running_desired_error = str(e)
            with self._state_lock:
                halted = bool(
                    self._portfolio_risk
                    and self._portfolio_risk.state.kill_switch_active)
                return {
                    "mode": self.mode,
                    "running_flag": running_flag,
                    "thread_alive": thread_alive,
                    "running_actual": thread_alive,
                    "running_desired": running_desired,
                    "running_desired_error": running_desired_error,
                    "paused": bool(self.paused),
                    "halted": halted,
                    "startup_error": self.startup_error,
                }
```

- [ ] **Step 4: Run focused + regression**

Run:
```bash
.venv/bin/python -m pytest tests/test_supervisor_autostart.py tests/test_supervisor_safety.py -q
.venv/bin/python -m pytest -q
```
Expected: PASS. Any existing assertion on the lifecycle dict still holds; `running_desired_error` is a new key (defaults `None`).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor_autostart.py
git commit -m "fix(lifecycle): lifecycle_state tolerates unreadable runtime store (running_desired=null + error)"
```

---

### Task 5: Web endpoints map incomplete lifecycle operations to HTTP 500

Implements handoff suggested-order step 6 and the endpoint halves of **Findings 1, 2, 4** ("the HTTP endpoint must not return `{"ok": true}` when the thread remains alive").

**Files:**
- Modify: `src/swingbot/web.py` (`/api/control/start`, `/api/control/stop`, imports)
- Test: `tests/test_web_desire.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_web_desire.py`, extend the fake controller used by the existing tests so it can simulate lifecycle failures, then add endpoint tests. Add to the fake controller class (the one with `request_start`/`request_stop` near the top of the file) the ability to raise on stop, and add:

```python
def test_stop_timeout_returns_500_not_ok(client_factory):
    from swingbot.supervisor import LifecycleError
    ctrl = FakeController()
    ctrl.stop_error = LifecycleError(
        "stop timed out; loop thread still alive", stop_timed_out=True)
    client = client_factory(ctrl)
    resp = client.post("/api/control/stop", headers=AUTH)
    assert resp.status_code == 500
    assert resp.json() != {"ok": True}
    assert "still alive" in resp.json()["detail"]


def test_start_persist_failure_returns_500(client_factory):
    from swingbot.supervisor import DesirePersistError
    ctrl = FakeController()
    ctrl.start_error = DesirePersistError(
        "started loop but failed to persist running_desired=true: disk full; "
        "loop rolled back", rolled_back=True)
    client = client_factory(ctrl)
    resp = client.post("/api/control/start", headers=AUTH)
    assert resp.status_code == 500
    assert "rolled back" in resp.json()["detail"]


def test_start_precondition_error_still_returns_400(client_factory):
    ctrl = FakeController()
    ctrl.start_error = RuntimeError("previous loop thread still alive")
    client = client_factory(ctrl)
    resp = client.post("/api/control/start", headers=AUTH)
    assert resp.status_code == 400
```

> **Engineer note:** Match the test file's existing fixtures. The current file builds a client and uses an auth header — reuse those exact names (`client_factory`/`AUTH` are illustrative; substitute whatever the file already defines, e.g. a module-level `client` and `_auth()` helper). The `FakeController` must apply `start_error`/`stop_error` inside `request_start`/`request_stop` (raise it if set). Extend the existing fake rather than adding a second one.

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
.venv/bin/python -m pytest tests/test_web_desire.py -k "timeout or persist_failure or precondition" -q
```
Expected: FAIL — `/api/control/stop` currently returns `{"ok": true}` unconditionally (no try/except), so a `LifecycleError` would 500 *uncaught* as a generic server error without the mapped detail, and the start mapping does not yet distinguish `LifecycleError` (500) from `RuntimeError` (400).

- [ ] **Step 3: Implement the endpoint mapping**

In `src/swingbot/web.py`, add the import near the other supervisor imports:

```python
from swingbot.supervisor import LifecycleError
```

Replace `control_start`:

```python
    @app.post("/api/control/start")
    def control_start(_=Depends(require_token)):
        # request_start serializes start + desire persistence under the supervisor
        # lifecycle lock; fall back to bare start() for fakes that lack it.
        try:
            if hasattr(controller, "request_start"):
                controller.request_start()
            else:
                controller.start()
        except LifecycleError as e:
            # Partial/incomplete lifecycle outcome (e.g. started-but-not-persisted,
            # rollback timed out). Report truthfully, never as success.
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            # Pre-condition failures (e.g. duplicate live thread) — bad request.
            raise HTTPException(status_code=400, detail=str(e))
        return {"ok": True}
```

Replace `control_stop`:

```python
    @app.post("/api/control/stop")
    def control_stop(_=Depends(require_token)):
        # request_stop clears desire then always stops; fall back to bare stop()
        # for fakes that lack it. An incomplete stop must not report success.
        try:
            if hasattr(controller, "request_stop"):
                controller.request_stop()
            else:
                controller.stop()
        except LifecycleError as e:
            raise HTTPException(status_code=500, detail=str(e))
        return {"ok": True}
```

(`LifecycleError` is a `RuntimeError` subclass, so the `except LifecycleError` in `control_start` must come **before** the broad `except Exception` — it does.)

- [ ] **Step 4: Run focused + regression**

Run:
```bash
.venv/bin/python -m pytest tests/test_web_desire.py -q
.venv/bin/python -m pytest -q
ruff check src tests
```
Expected: PASS; ruff clean. Existing `test_failed_request_start_surfaces_400` still passes (its fake raises a plain exception → 400 branch).

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/web.py tests/test_web_desire.py
git commit -m "fix(web): map incomplete lifecycle ops to HTTP 500 with actionable detail; never ok:true on live thread"
```

---

### Task 6: Lifecycle GET exposes captured failures end-to-end

Implements the handoff "Required regression test" for **Finding 3** at the HTTP boundary, and the "Verification Required After Fixes" item 6.

**Files:**
- Test: `tests/test_web_desire.py` (and/or `tests/test_web_lifespan.py` if the lifecycle GET is exercised there)

- [ ] **Step 1: Write the test**

In `tests/test_web_desire.py`, add a controller-backed lifecycle GET assertion. Use the existing fake-controller wiring; have the fake return a `lifecycle_state()` dict representing an unreadable store:

```python
def test_lifecycle_endpoint_exposes_unreadable_desire(client_factory):
    ctrl = FakeController()
    ctrl._lifecycle = {
        "mode": "paper", "running_flag": False, "thread_alive": False,
        "running_actual": False, "running_desired": None,
        "running_desired_error": "runtime-state read failed",
        "paused": False, "halted": False,
        "startup_error": "auto-start failed: runtime-state read failed",
    }
    client = client_factory(ctrl)
    resp = client.get("/api/control/lifecycle")
    assert resp.status_code == 200
    body = resp.json()
    assert body["running_desired"] is None
    assert body["running_desired_error"] == "runtime-state read failed"
    assert "runtime-state read failed" in body["startup_error"]
```

> **Engineer note:** The existing `FakeController` already exposes a `lifecycle_state()` returning `self._lifecycle` (see current `test_web_desire.py` line ~10). Set the dict fields above; do not add a new fake.

- [ ] **Step 2: Run the test**

Run:
```bash
.venv/bin/python -m pytest tests/test_web_desire.py::test_lifecycle_endpoint_exposes_unreadable_desire -q
```
Expected: PASS immediately (the lifecycle GET passes the controller dict straight through; this test pins the contract so a future change can't silently drop the error field). If it FAILS because the endpoint reshapes the dict, fix the endpoint to pass `lifecycle_state()` through unchanged.

- [ ] **Step 3: Commit**

```bash
git add tests/test_web_desire.py
git commit -m "test(web): pin lifecycle GET exposing running_desired=null + error + startup_error"
```

---

### Task 7: Full verification, deploy, and roadmap update

Implements the handoff "Verification Required After Fixes" gate (commands + manual checks 1–6) and the project's standing docker-rebuild policy.

**Files:**
- Modify: `docs/ROADMAP_STATUS.md`

- [ ] **Step 1: Run the full handoff verification gate**

```bash
.venv/bin/python -m pytest -q \
  tests/test_runtime_state.py \
  tests/test_supervisor_autostart.py \
  tests/test_supervisor_safety.py \
  tests/test_web_desire.py \
  tests/test_web_lifespan.py

.venv/bin/python -m pytest -q
ruff check src tests
cd frontend && npm run build && cd ..
```
Expected: targeted lifecycle suite all green; full suite green (≥ the prior 420 passed, 6 skipped, plus the new failure-path tests); ruff clean; frontend build OK.

- [ ] **Step 2: Rebuild + restart the container (standing policy — pre-authorized)**

```bash
docker compose build swingbot && docker compose up -d swingbot
```

- [ ] **Step 3: Live-verify the six handoff acceptance checks on `:8000`**

Programmatically confirm against the running container (use the existing token/auth):
1. Successful Start → `GET /api/control/lifecycle` shows `running_actual=true` and `running_desired=true`.
2. (Fault-injection, optional in prod) a failed desire write during Start leaves no active loop — covered by Task 2 tests; note here that prod cannot easily inject disk-full.
3. Successful Stop → `running_actual=false`, `running_desired=false`, no live thread.
4. A Stop timeout is visibly reported (HTTP 500) and blocks a second Start — covered by Tasks 1/3/5 tests.
5. A desire-write failure during Stop still stops the loop — covered by Task 3 test.
6. A runtime-state read failure stays visible through `GET /api/control/lifecycle` (`running_desired=null`, `running_desired_error`/`startup_error` populated) — covered by Tasks 4/6 tests.

Record the live `lifecycle` JSON in the commit message / roadmap note. Leave the bot **running + desired** so the next rebuild auto-resumes (per Phase 2 convention).

- [ ] **Step 4: Refresh the semantic graph (project rule)**

```bash
python3 -m graphify update .
```

- [ ] **Step 5: Update `docs/ROADMAP_STATUS.md`**

Set the NEXT ACTION to record Phase 2.1 done and that the Phase 3 plan is now the next deliverable. Replace the Phase 2 NEXT-ACTION paragraph's trailing "NEXT: write the Phase 3 plan" with a short Phase 2.1 completion note (suite count, the six live checks, commit hashes) followed by the unchanged Phase 3 pointer (spec §5 Phase 3; basis `specs/2026-06-13-visible-autonomous-entry-design-reviewed.md`).

- [ ] **Step 6: Commit + push**

```bash
git add docs/ROADMAP_STATUS.md docs/superpowers/plans/2026-06-14-phase2-lifecycle-code-review-handoff.md graphify-out
git commit -m "docs: Phase 2.1 lifecycle hardening complete; lifecycle truth layer ready for Phase 3"
git push origin master
```

---

## Self-Review (completed against the handoff)

**Finding coverage:**
- Finding 1 (Start partial success) → Task 2 (rollback + don't-clear-startup_error) + Task 5 (HTTP 500).
- Finding 2 (Stop reports success while alive; `running_actual` semantics) → Task 1 (`stop()` bool + `running_actual=thread_alive` + `running_flag`) + Task 3 (request_stop timeout surfaced) + Task 5 (endpoint ≠ ok:true).
- Finding 3 (captured runtime read failure unobservable) → Task 4 (tolerant `lifecycle_state`) + Task 6 (HTTP exposure).
- Finding 4 (Stop skipped when persistence fails) → Task 3 (always-stop + combined errors).
- Suggested order steps 1–7 → Task 1 (exceptions + running_actual), 2/3 (request_*), 4 (tolerance), 5 (endpoints), tests-before-expectations honored per task.

**Existing tests flagged by the handoff:**
- `test_supervisor_safety.py` join-timeout test → updated in Task 1 to the reviewed contract.
- `test_supervisor_autostart.py` → extended in Tasks 2/3/4.
- `test_web_desire.py` → extended in Tasks 5/6.
- `test_runtime_state.py` concurrency test → kept as-is (handoff says keep, do not over-claim transactional proof); no change needed.

**Guardrails honored:** no strategy-behavior change; lifecycle→state lock order preserved (no new lock, no reordering); duplicate loop threads still prevented (thread reference retained on timeout, Task 1); halt/pause/resume/shutdown untouched; auto-start stays paper-only/failure-tolerant (`auto_start_if_desired` not modified); default `running_desired=false` preserved (no store-default change). No exception is swallowed and no path returns `ok:true` with an error string.

**Type consistency:** `LifecycleError(message, *, persist_error, stop_timed_out, rolled_back)` and `DesirePersistError(LifecycleError)` defined in Task 1, raised in Tasks 2/3, imported in Task 5; `stop() -> bool` defined Task 1, consumed in Tasks 1 (`set_mode`), 2 (rollback), 3 (request_stop); `running_flag`/`running_actual`/`running_desired_error` keys defined Tasks 1/4 and asserted in Tasks 1/4/6.
