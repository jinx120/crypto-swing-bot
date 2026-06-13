# Visible Autonomous Entry Phase 0 + Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the trading loop safe to run autonomously later, without changing strategy behavior: serialize supervisor state mutations, make lifecycle transitions race-safe and promptly stoppable, stop treating broker failures as a flat account, and give FastAPI sole ownership of background-thread startup/shutdown.

**Architecture:** `PortfolioSupervisor` gets two locks with one documented order: lifecycle operations (`start`, `stop`, `set_mode`) are serialized by a lifecycle `RLock`, while trading state and strategy structures are protected by a state `RLock`. A `threading.Event` wakes the loop immediately on stop; a timed-out stop retains the live thread reference and cannot change mode or permit a duplicate start. `AlpacaBroker.get_position()` returns `None` only for Alpaca's confirmed HTTP 404. FastAPI lifespan owns poller startup and supervisor/poller shutdown.

**Tech Stack:** Python 3.11+, FastAPI/Starlette lifespan, `threading.RLock`, `threading.Event`, `alpaca-py`, pytest, FastAPI `TestClient`.

**Scope:** This plan covers only safety hardening before autonomous startup. It does not persist desired-running state, auto-start the supervisor, add trading telemetry, change strategies, or rebuild the dashboard.

**Important implementation rule:** Never acquire `_lifecycle_lock` while holding `_state_lock`. Lifecycle methods acquire lifecycle first and may then acquire state. The loop and ordinary state methods acquire only state. This prevents a stop/start/mode-switch deadlock while a tick is running.

---

## Review Corrections Incorporated

This revision corrects these problems in the previous draft:

1. A single `RLock` did not serialize lifecycle operations while `stop()` joined outside that lock.
2. `time.sleep(poll_seconds)` meant normal stops would often time out for up to 60 seconds.
3. `set_mode()` was not guarded and could change mode while the old loop remained alive.
4. The concurrency test used `halt()` even though the required risky operation is `reload()`.
5. `running_actual` was incorrectly defined as the internal `_running` flag rather than a live loop thread.
6. Lifespan shutdown stopped the poller before the trading supervisor and did not guarantee poller cleanup if supervisor shutdown raised.
7. The plan committed intentionally failing test-only commits, leaving broken intermediate commits.
8. The Docker acceptance expected candle-poller activity in logs, but the poller logs only errors.
9. The roadmap path incorrectly included an extra `crypto-swing-bot/` prefix.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/swingbot/broker/alpaca.py` | Broker position truth | Return `None` only for `APIError.status_code == 404`; propagate all other failures |
| `src/swingbot/supervisor.py` | Trading-state synchronization and loop lifecycle | Add state/lifecycle locks, stop event, interruptible loop, guarded methods, duplicate-loop prevention, safe mode switching, lifecycle inspection |
| `src/swingbot/web.py` | HTTP app and process lifecycle | Add FastAPI lifespan accepting `poller=`, start poller, stop supervisor then poller with guaranteed cleanup |
| `src/swingbot/webmain.py` | Composition root | Pass poller into `create_app`; remove direct `poller.start()` |
| `tests/test_alpaca_broker.py` | Broker truth tests | Add confirmed-404 and propagated-error cases |
| `tests/test_supervisor_safety.py` | New supervisor safety suite | Add reload serialization, prompt/idempotent stop, timeout retention, duplicate-start, safe mode-switch, missing-credentials, lifecycle-state tests |
| `tests/test_web_lifespan.py` | New lifespan suite | Verify startup/shutdown ownership and cleanup ordering |
| `docs/ROADMAP_STATUS.md` | Project status | Mark Phase 0/1 complete only after all gates pass |

No new production module is needed in this phase.

---

## Phase 0 Rule

For every task below:

1. Add the focused test.
2. Run it and confirm the documented failure against the current implementation.
3. Implement the smallest production change.
4. Run the focused and regression tests.
5. Commit the passing test and implementation together.

Do not commit deliberately red test-only commits.

---

### Task 1: Make Broker Position Lookup Truthful

**Files:**
- Modify: `src/swingbot/broker/alpaca.py:3-5`
- Modify: `src/swingbot/broker/alpaca.py:28-35`
- Test: `tests/test_alpaca_broker.py`

- [ ] **Step 1: Add failing broker-truth tests**

Append to `tests/test_alpaca_broker.py`:

```python
from alpaca.common.exceptions import APIError
from swingbot.broker.alpaca import AlpacaBroker


class _HttpError:
    def __init__(self, status_code):
        self.response = type("Response", (), {"status_code": status_code})()


class _PositionClient:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def get_open_position(self, symbol):
        if self.error is not None:
            raise self.error
        return self.result


def _api_error(status_code):
    return APIError('{"code": 1, "message": "request failed"}',
                    _HttpError(status_code))


def _broker_with_client(client):
    broker = object.__new__(AlpacaBroker)
    broker._client = client
    return broker


def test_get_position_returns_none_only_for_confirmed_404():
    broker = _broker_with_client(_PositionClient(error=_api_error(404)))
    assert broker.get_position("BTC/USD") is None


def test_get_position_propagates_non_404_api_error():
    broker = _broker_with_client(_PositionClient(error=_api_error(500)))
    with pytest.raises(APIError):
        broker.get_position("BTC/USD")


def test_get_position_propagates_transport_error():
    broker = _broker_with_client(_PositionClient(error=ConnectionError("network down")))
    with pytest.raises(ConnectionError):
        broker.get_position("BTC/USD")


def test_get_position_serializes_confirmed_position():
    position = type("Position", (), {
        "qty": "0.25",
        "avg_entry_price": "50000",
        "market_value": "12500",
    })()
    broker = _broker_with_client(_PositionClient(result=position))
    assert broker.get_position("BTC/USD") == {
        "symbol": "BTC/USD",
        "qty": 0.25,
        "avg_entry_price": 50000.0,
        "market_value": 12500.0,
    }
```

- [ ] **Step 2: Verify the current unsafe behavior**

Run:

```bash
.venv/bin/python -m pytest tests/test_alpaca_broker.py -k get_position -q
```

Expected: the non-404 and transport-error tests fail because current code returns `None` for every exception.

- [ ] **Step 3: Implement confirmed-404-only handling**

Add this import in `src/swingbot/broker/alpaca.py`:

```python
from alpaca.common.exceptions import APIError
```

Replace `get_position()` with:

```python
    def get_position(self, symbol: str) -> dict | None:
        """Return None only when Alpaca confirms that no position exists."""
        try:
            p = self._client.get_open_position(normalize_symbol(symbol))
        except APIError as exc:
            if exc.status_code == 404:
                return None
            raise
        return {"symbol": symbol, "qty": float(p.qty),
                "avg_entry_price": float(p.avg_entry_price),
                "market_value": float(p.market_value)}
```

- [ ] **Step 4: Verify focused and reconciliation behavior**

Run:

```bash
.venv/bin/python -m pytest tests/test_alpaca_broker.py tests/test_orchestrator.py -q
```

Expected: PASS. A broker failure now propagates through reconciliation instead of being interpreted as confirmed-flat.

- [ ] **Step 5: Commit**

```bash
git add src/swingbot/broker/alpaca.py tests/test_alpaca_broker.py
git commit -m "fix: distinguish missing broker position from broker failure"
```

---

### Task 2: Add Supervisor Safety Tests

**Files:**
- Create: `tests/test_supervisor_safety.py`
- Reuse test helpers from: `tests/test_supervisor.py`

- [ ] **Step 1: Create the safety test module**

Create `tests/test_supervisor_safety.py`:

```python
import threading
import time

import pytest

from swingbot.profiles import ProfileStore
from swingbot.supervisor import PortfolioSupervisor
from tests.test_supervisor import FakeBroker, FakeMarket, _bars, _profile


class NoCredentials:
    def get(self):
        return None


def _supervisor(tmp_path, *, broker=None, creds=None, mode="paper"):
    profiles = ProfileStore(str(tmp_path / "profiles.db"))
    profiles.save("btc", _profile("BTC/USD"))
    profiles.arm("btc")
    market = FakeMarket({"BTC/USD": _bars()})
    return PortfolioSupervisor(
        profiles=profiles,
        creds=creds,
        state_db=str(tmp_path / "state.db"),
        market=market,
        broker=broker if broker is not None else FakeBroker(),
        mode=mode,
    )


def _install_stubborn_thread(sup):
    release = threading.Event()
    thread = threading.Thread(target=release.wait, daemon=True)
    sup._thread = thread
    sup._running = True
    thread.start()
    return thread, release


def test_reload_waits_for_inflight_tick(tmp_path):
    sup = _supervisor(tmp_path)
    sup.build()
    tick_entered = threading.Event()
    release_tick = threading.Event()
    reload_finished = threading.Event()

    strategy = sup._strategies["btc"]
    original_tick = strategy["orch"].tick

    def blocking_tick(now):
        tick_entered.set()
        assert release_tick.wait(timeout=2)
        original_tick(now)

    strategy["orch"].tick = blocking_tick
    tick_thread = threading.Thread(target=sup.tick_all)
    tick_thread.start()
    assert tick_entered.wait(timeout=2)

    reload_thread = threading.Thread(
        target=lambda: (sup.reload(), reload_finished.set()))
    reload_thread.start()
    time.sleep(0.1)
    assert not reload_finished.is_set()

    release_tick.set()
    tick_thread.join(timeout=2)
    reload_thread.join(timeout=2)
    assert not tick_thread.is_alive()
    assert not reload_thread.is_alive()
    assert reload_finished.is_set()


def test_stop_interrupts_loop_sleep_and_is_idempotent(tmp_path):
    sup = _supervisor(tmp_path)
    ticked = threading.Event()
    sup.tick_all = ticked.set
    sup._poll_seconds = lambda: 60

    sup.start()
    assert ticked.wait(timeout=2)
    started = time.monotonic()
    sup.stop()
    elapsed = time.monotonic() - started
    sup.stop()

    assert elapsed < 0.5
    assert sup._thread is None
    assert sup.lifecycle_state()["running_actual"] is False


def test_stop_retains_live_thread_after_join_timeout(tmp_path):
    sup = _supervisor(tmp_path)
    sup._join_timeout = 0.05
    thread, release = _install_stubborn_thread(sup)
    try:
        sup.stop()
        assert sup._thread is thread
        assert thread.is_alive()
        state = sup.lifecycle_state()
        assert state["running_flag"] is False
        assert state["thread_alive"] is True
        assert state["running_actual"] is False
    finally:
        release.set()
        thread.join(timeout=2)


def test_start_refuses_while_prior_thread_is_alive(tmp_path):
    sup = _supervisor(tmp_path)
    thread, release = _install_stubborn_thread(sup)
    sup._running = False
    try:
        with pytest.raises(RuntimeError, match="previous loop thread still alive"):
            sup.start()
    finally:
        release.set()
        thread.join(timeout=2)


def test_mode_does_not_change_when_stop_times_out(tmp_path):
    sup = _supervisor(tmp_path, mode="live")
    sup._join_timeout = 0.05
    thread, release = _install_stubborn_thread(sup)
    try:
        ok, reason = sup.set_mode("paper")
        assert ok is False
        assert "still alive" in reason
        assert sup.mode == "live"
    finally:
        release.set()
        thread.join(timeout=2)


def test_start_without_credentials_leaves_no_loop(tmp_path):
    sup = _supervisor(tmp_path, broker=FakeBroker())
    sup._broker = None
    sup.creds = NoCredentials()

    with pytest.raises(RuntimeError, match="credentials not set"):
        sup.start()

    state = sup.lifecycle_state()
    assert state["running_flag"] is False
    assert state["thread_alive"] is False
    assert state["running_actual"] is False


def test_lifecycle_state_reports_running_pause_and_halt(tmp_path):
    sup = _supervisor(tmp_path)
    ticked = threading.Event()
    sup.tick_all = ticked.set
    sup._poll_seconds = lambda: 60

    sup.start()
    try:
        assert ticked.wait(timeout=2)
        running = sup.lifecycle_state()
        assert running["running_flag"] is True
        assert running["thread_alive"] is True
        assert running["running_actual"] is True

        sup.pause()
        assert sup.lifecycle_state()["paused"] is True
        sup.halt()
        assert sup.lifecycle_state()["halted"] is True
    finally:
        sup.stop()
```

- [ ] **Step 2: Run the safety suite and record the failures**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_safety.py -q
```

Expected failures against current code:

- reload completes while the tick is still blocked;
- stop takes approximately the join timeout because loop sleep is not interruptible;
- stop clears a still-live thread reference;
- start permits a second thread when `_running` is false;
- mode changes even though the previous loop remains alive;
- `lifecycle_state()` does not exist.

Do not commit yet.

---

### Task 3: Serialize Supervisor State

**Files:**
- Modify: `src/swingbot/supervisor.py:1-24`
- Modify: `src/swingbot/supervisor.py:76-92`
- Modify: state-reading/mutating methods in `src/swingbot/supervisor.py`
- Test: `tests/test_supervisor_safety.py::test_reload_waits_for_inflight_tick`

- [ ] **Step 1: Add a reusable state-lock decorator**

Add `wraps` to the imports and define this helper immediately before `PortfolioSupervisor`:

```python
from functools import wraps


def _state_locked(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._state_lock:
            return method(self, *args, **kwargs)
    return wrapped
```

- [ ] **Step 2: Initialize synchronization primitives**

Append these fields to `PortfolioSupervisor.__init__`:

```python
        # Lock order: lifecycle -> state. Never acquire lifecycle while holding state.
        self._lifecycle_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._join_timeout = 2.0
```

- [ ] **Step 3: Guard state methods**

Add `@_state_locked` directly above each of these existing methods without changing their bodies:

```python
    build
    tick_all
    status
    journal
    metrics
    halt
    reset
    flatten
    reload
    pause
    resume
```

Do not decorate `set_mode`, `start`, or `stop`; Task 4 gives them lifecycle-aware implementations.
Do not decorate internal helpers such as `_warm`, `_snapshot`, `_build_summary`, `_trades`,
`_make_gate`, or `_make_on_close`; they are called from an already state-locked public method.

- [ ] **Step 4: Verify reload serialization**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_safety.py::test_reload_waits_for_inflight_tick -q
```

Expected: PASS.

- [ ] **Step 5: Run state/control regressions**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor.py tests/test_supervisor_control.py tests/test_web_portfolio.py -q
```

Expected: PASS.

- [ ] **Step 6: Keep this slice uncommitted until Task 4**

`tests/test_supervisor_safety.py` intentionally also contains the lifecycle tests completed by
Task 4. Committing here would create a red intermediate commit. Continue directly to Task 4 and
commit the complete passing supervisor-safety slice there.

---

### Task 4: Make Loop Lifecycle Prompt, Idempotent, and Race-Safe

**Files:**
- Modify: `src/swingbot/supervisor.py:294-315`
- Modify: `src/swingbot/supervisor.py:327-364`
- Test: `tests/test_supervisor_safety.py`

- [ ] **Step 1: Replace `start`, add `_run_loop`, and replace `stop`**

Replace the existing `start()` and `stop()` methods with:

```python
    def start(self) -> None:
        with self._lifecycle_lock:
            if self._running:
                return
            if self._thread is not None and self._thread.is_alive():
                raise RuntimeError(
                    "previous loop thread still alive; refusing to start a second loop")

            with self._state_lock:
                self.build()
                for s in self._strategies.values():
                    s["orch"].reconcile(datetime.now(timezone.utc))

            self._stop_event.clear()
            self._running = True
            self._thread = threading.Thread(
                target=self._run_loop, name="swingbot-supervisor", daemon=True)
            try:
                self._thread.start()
            except Exception:
                self._running = False
                self._stop_event.set()
                self._thread = None
                raise

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick_all()
            except Exception as e:
                print(f"[supervisor] cycle error: {e}")
                traceback.print_exc()
            with self._state_lock:
                delay = self._poll_seconds()
            if self._stop_event.wait(delay):
                break

    def stop(self) -> None:
        # Lifecycle lock remains held across join so concurrent start/set_mode
        # cannot race this transition. Do not take the state lock here: a hung
        # tick may hold it, and stop must still signal and time out.
        with self._lifecycle_lock:
            self._running = False
            self._stop_event.set()
            thread = self._thread
            if thread is None:
                return
            if thread is threading.current_thread():
                return
            thread.join(timeout=self._join_timeout)
            if not thread.is_alive() and self._thread is thread:
                self._thread = None
```

- [ ] **Step 2: Replace `set_mode()` so a timed-out stop cannot change mode**

Replace the existing `set_mode()` method with:

```python
    def set_mode(self, mode: str) -> tuple[bool, str]:
        with self._lifecycle_lock:
            if mode not in ("paper", "live"):
                return (False, "mode must be 'paper' or 'live'")

            with self._state_lock:
                if mode == "live":
                    ok, reason = can_go_live(compute_metrics(self._trades()))
                    if not ok:
                        return (False, f"go-live blocked: {reason}")
                was_running = self._running

            self.stop()
            if self._thread is not None and self._thread.is_alive():
                return (False, "previous loop thread still alive; mode unchanged")

            with self._state_lock:
                self.mode = mode
                self._broker = None

            if was_running:
                self.start()
            else:
                self.build()
            return (True, f"mode set to {mode}")
```

`_lifecycle_lock` is an `RLock`, so `set_mode()` may safely call `stop()` and `start()`. Both
methods may then acquire `_state_lock`, preserving the required lifecycle-to-state lock order.

- [ ] **Step 3: Add truthful lifecycle inspection**

Add this method immediately after `status()`:

```python
    def lifecycle_state(self) -> dict:
        with self._lifecycle_lock:
            thread_alive = bool(self._thread is not None and self._thread.is_alive())
            running_flag = bool(self._running)
            with self._state_lock:
                halted = bool(
                    self._portfolio_risk
                    and self._portfolio_risk.state.kill_switch_active)
                return {
                    "mode": self.mode,
                    "running_flag": running_flag,
                    "thread_alive": thread_alive,
                    "running_actual": running_flag and thread_alive,
                    "paused": bool(self.paused),
                    "halted": halted,
                }
```

- [ ] **Step 4: Verify lifecycle safety tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_supervisor_safety.py -q
```

Expected: PASS.

- [ ] **Step 5: Verify supervisor and control regressions**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_supervisor.py \
  tests/test_supervisor_control.py \
  tests/test_web_control.py \
  tests/test_web_portfolio.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/supervisor.py tests/test_supervisor_safety.py
git commit -m "feat: harden supervisor loop lifecycle"
```

---

### Task 5: Give FastAPI Sole Ownership of Background Threads

**Files:**
- Modify: `src/swingbot/web.py:1-18`
- Modify: `src/swingbot/web.py:91-94`
- Modify: `src/swingbot/webmain.py:47-51`
- Modify: `src/swingbot/webmain.py:90-94`
- Create: `tests/test_web_lifespan.py`

- [ ] **Step 1: Add failing lifespan tests**

Create `tests/test_web_lifespan.py`:

```python
import pytest
from fastapi.testclient import TestClient

from swingbot.web import create_app


class RecordingController:
    def __init__(self, events, stop_error=None):
        self.events = events
        self.stop_error = stop_error

    def status(self):
        return {}

    def journal(self, strategy=None):
        return []

    def metrics(self, strategy=None):
        return {}

    def stop(self):
        self.events.append("controller:stop")
        if self.stop_error is not None:
            raise self.stop_error


class RecordingPoller:
    def __init__(self, events):
        self.events = events

    def start(self):
        self.events.append("poller:start")

    def stop(self):
        self.events.append("poller:stop")


def test_lifespan_starts_poller_then_stops_controller_before_poller():
    events = []
    app = create_app(
        RecordingController(events), profiles=None, creds=None, token="t",
        poller=RecordingPoller(events))

    with TestClient(app) as client:
        assert events == ["poller:start"]
        assert client.get("/api/state").status_code == 200

    assert events == ["poller:start", "controller:stop", "poller:stop"]


def test_lifespan_stops_poller_even_when_controller_stop_raises():
    events = []
    app = create_app(
        RecordingController(events, RuntimeError("stop failed")),
        profiles=None, creds=None, token="t", poller=RecordingPoller(events))

    with pytest.raises(RuntimeError, match="stop failed"):
        with TestClient(app):
            pass

    assert events == ["poller:start", "controller:stop", "poller:stop"]


def test_lifespan_allows_no_poller():
    events = []
    app = create_app(
        RecordingController(events), profiles=None, creds=None, token="t")
    with TestClient(app):
        pass
    assert events == ["controller:stop"]
```

- [ ] **Step 2: Verify the current app has no lifespan ownership**

Run:

```bash
.venv/bin/python -m pytest tests/test_web_lifespan.py -q
```

Expected: FAIL because `create_app()` does not accept `poller=`.

- [ ] **Step 3: Add FastAPI lifespan**

Add this standard-library import near the top of `src/swingbot/web.py`:

```python
from contextlib import asynccontextmanager
```

Replace the `create_app()` signature and initial `FastAPI(...)` construction with:

```python
def create_app(controller, profiles, creds, token: str, store=None, market=None,
               backfiller=None, discovery=None, discovery_cache_path=None,
               brain=None, agent_dir=None, poller=None) -> FastAPI:
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

    app = FastAPI(title="swingbot", lifespan=lifespan)
```

- [ ] **Step 4: Move poller startup from `webmain` into lifespan**

In `src/swingbot/webmain.py`, replace:

```python
    poller = CandlePoller(market, profiles)        # keeps all armed symbols warm for charts
    poller.start()
```

with:

```python
    poller = CandlePoller(market, profiles)        # lifespan owns start/stop
```

Add `poller=poller` to the existing `create_app(...)` call:

```python
    app = create_app(controller=supervisor, profiles=profiles, creds=creds,
                     token=token, store=store, market=market, backfiller=backfiller,
                     discovery=discovery,
                     discovery_cache_path=os.path.join(DATA_DIR, "discovery.json"),
                     brain=brain, agent_dir=os.path.join(DATA_DIR, "agent"),
                     poller=poller)
```

- [ ] **Step 5: Verify lifespan and web regressions**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_web_lifespan.py \
  tests/test_web_read.py \
  tests/test_web_control.py \
  tests/test_web_portfolio.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/swingbot/web.py src/swingbot/webmain.py tests/test_web_lifespan.py
git commit -m "feat: own background threads in FastAPI lifespan"
```

---

### Task 6: Full Regression and Deployment Verification

**Files:**
- Modify after verification: `docs/ROADMAP_STATUS.md`

- [ ] **Step 1: Run the complete Python suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: PASS. If an unrelated pre-existing failure appears, verify it against the base commit
before documenting it as pre-existing.

- [ ] **Step 2: Build the frontend**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 3: Rebuild and restart the container**

Run:

```bash
docker compose build swingbot
docker compose up -d swingbot
docker compose ps
docker compose logs --tail=50 swingbot
```

Expected:

- `swingbot` container is running;
- web server starts without lifespan errors;
- logs contain no duplicate-loop, poller, or shutdown errors.

This phase intentionally does **not** auto-start the supervisor.

- [ ] **Step 4: Verify clean shutdown and restart**

Run:

```bash
docker compose restart swingbot
docker compose ps
docker compose logs --tail=80 swingbot
```

Expected: restart completes promptly; logs contain no leaked-thread or duplicate-loop error.

- [ ] **Step 5: Update the roadmap**

Update `docs/ROADMAP_STATUS.md` to mark Visible Autonomous Entry Phase 0/1 safety hardening
complete and set the next action to the Phase 2 plan: persisted desire and paper-mode auto-resume.

- [ ] **Step 6: Commit roadmap status**

```bash
git add docs/ROADMAP_STATUS.md
git commit -m "docs: mark autonomous entry safety hardening complete"
```

---

## Self-Review Checklist

Before execution handoff, confirm:

- [ ] Every lifecycle transition is serialized by `_lifecycle_lock`.
- [ ] Every strategy/state mutation is serialized by `_state_lock`.
- [ ] No code path acquires lifecycle while holding state.
- [ ] `stop()` can signal and time out even if a tick is hung while holding state.
- [ ] Loop sleep is interruptible with `_stop_event.wait(...)`.
- [ ] A timed-out stop retains the live thread reference.
- [ ] A timed-out mode switch leaves mode and broker unchanged.
- [ ] `running_actual` requires both the running flag and a live thread.
- [ ] Broker 404 is the only exception converted to `None`.
- [ ] FastAPI stops the supervisor before the poller and always attempts poller cleanup.
- [ ] No deliberately failing commit is created.
- [ ] No strategy, desired-running, telemetry, or dashboard behavior is changed.

---

## Execution Handoff

Plan revised at `/home/ahmad/2026-06-13-visible-autonomous-entry-phase-0-1.md`.

Recommended execution approach: use `superpowers:subagent-driven-development` task-by-task, with
review after each passing commit. Inline execution with `superpowers:executing-plans` is also
valid.
