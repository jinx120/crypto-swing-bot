# Phase 2 Lifecycle Code Review Handoff

**Date:** 2026-06-14  
**Repository:** `jinx120/crypto-swing-bot`  
**Reviewed head:** `2f13bda35d5730ddc37fdc1584335d6228c4b44f`  
**Review range:** `68077ecb02665ea647f959c877559c9184a26c54..2f13bda`  
**Primary focus:** Visible Autonomous Entry Phase 2 and the latest correction commit

## Objective

Fix the remaining lifecycle failure-path defects without weakening the concurrency
serialization introduced by `2f13bda`.

The current happy paths and concurrent Start/Stop ordering are sound. The remaining
problems occur when durable-state persistence fails, runtime-state reads fail, or a
supervisor thread does not stop before the join timeout.

## Required Findings To Address

### 1. High: Failed desire persistence leaves Start partially successful

**Location:** `src/swingbot/supervisor.py`, `PortfolioSupervisor.request_start()`

Current order:

```python
self.start()
self.mark_desired(True)
```

If `mark_desired(True)` raises after `start()` succeeds, the API returns HTTP 400 but
the trading loop remains active with `running_desired=false`.

Reproduced state:

```text
start_response: 400 {"detail": "disk full"}
running_actual: true
running_desired: false
```

This violates the documented claim that explicit Start and desire persistence form
one lifecycle operation. It is especially dangerous because a client receives a
failure response while trading continues.

**Required behavior:**

- A successful explicit Start must end with both the loop running and
  `running_desired=true`.
- If persisting `running_desired=true` fails, roll back the newly started loop.
- If rollback also fails or times out, surface both failures clearly. Do not report a
  simple Start failure while leaving an unexplained live thread.
- Do not clear a stale `startup_error` unless the explicit Start operation fully
  succeeds.

**Required regression test:**

- Use a runtime-state fake whose `set_running_desired(True)` raises.
- Assert the Start request raises/fails.
- Assert no supervisor thread remains alive after successful rollback.
- Assert `running_actual` is false.

### 2. High: Stop reports success while the loop thread remains alive

**Locations:**

- `src/swingbot/supervisor.py`, `PortfolioSupervisor.stop()` / `request_stop()`
- `src/swingbot/web.py`, `POST /api/control/stop`

`stop()` silently returns after its join timeout. `request_stop()` and the endpoint
then return success even if the thread is still alive and may still be executing a
broker operation.

Reproduced state:

```text
stop_response: 200 {"ok": true}
thread_alive: true
running_flag: false
running_actual: false
```

The existing `running_actual` calculation is also misleading. The reviewed design
defines `running_actual` as whether the loop thread is alive, but the implementation
uses `running_flag and thread_alive`.

**Required behavior:**

- A timed-out Stop must be distinguishable from a completed Stop.
- The HTTP endpoint must not return `{"ok": true}` when the thread remains alive.
- Keep the live thread reference so duplicate starts remain blocked.
- Report `running_actual` according to the reviewed contract: whether the loop thread
  is alive. Keep `running_flag` separately if useful.
- Preserve the requirement that an explicit Stop clears durable desire, even when the
  current process cannot immediately stop the thread.

**Required regression tests:**

- Install a stubborn thread and force a short join timeout.
- Assert explicit Stop reports failure or an explicit incomplete/timeout result.
- Assert the endpoint does not return a successful response.
- Assert lifecycle state reports `thread_alive=true` and `running_actual=true`.
- Assert a later Start remains rejected while that thread is alive.

### 3. Medium: Captured runtime-state read failures cannot be observed

**Locations:**

- `src/swingbot/supervisor.py`, `auto_start_if_desired()`
- `src/swingbot/supervisor.py`, `lifecycle_state()`
- `src/swingbot/web.py`, `GET /api/control/lifecycle`

`auto_start_if_desired()` captures a runtime-state read failure into `startup_error`.
However, `lifecycle_state()` reads the same failing store again before returning the
captured error, causing the lifecycle endpoint itself to fail.

Reproduced state:

```text
startup_error: auto-start failed: runtime-state read failed
lifecycle_error: RuntimeError runtime-state read failed
```

**Required behavior:**

- The lifecycle endpoint must remain usable when the runtime-state store cannot be
  read.
- It must expose the captured `startup_error`.
- Represent unreadable desire explicitly, for example with `running_desired=null` and
  an additional error field, rather than silently returning false.

**Required regression test:**

- Use a runtime-state fake whose `get_running_desired()` raises.
- Call `auto_start_if_desired()`.
- Call `lifecycle_state()` and the lifecycle HTTP endpoint.
- Assert both return successfully and expose the runtime-state failure.

### 4. Medium: Explicit Stop is skipped when desire persistence fails

**Location:** `src/swingbot/supervisor.py`, `PortfolioSupervisor.request_stop()`

Current order:

```python
self.mark_desired(False)
self.stop()
```

If clearing durable desire raises, `stop()` is never attempted and the bot continues
trading despite an explicit Stop request.

**Required behavior:**

- Always attempt to stop the current process after an explicit Stop request.
- Still attempt to clear durable desire before stopping, preserving the restart
  safety intent.
- If persistence fails, surface that restart may auto-resume unexpectedly.
- If stop also fails or times out, surface both failures.

**Required regression tests:**

- Use a runtime-state fake whose `set_running_desired(False)` raises.
- Assert `stop()` is still attempted.
- Assert the request reports the persistence failure.
- Cover the combined persistence-failure plus stop-timeout case.

## Suggested Implementation Order

1. Define explicit lifecycle-operation results or dedicated exceptions for:
   successful stop, stop timeout, desire persistence failure, and combined failures.
2. Correct `running_actual` semantics in `lifecycle_state()`.
3. Make lifecycle-state reporting tolerate runtime-state read failures.
4. Make `request_stop()` attempt both persistence and stopping while preserving both
   errors.
5. Make `request_start()` roll back a newly started loop when persistence fails.
6. Update the web endpoints to map incomplete lifecycle operations to non-success
   responses with actionable details.
7. Add failure-path tests before adjusting existing expectations.

Avoid solving these issues by swallowing exceptions or returning `ok: true` with an
error string. Operator-facing lifecycle commands must report truthful outcomes.

## Existing Tests That Need Adjustment Or Extension

- `tests/test_supervisor_autostart.py`
  - Existing tests cover `start()` failure but not persistence failure after Start.
  - Add Start rollback and Stop persistence-failure tests.
- `tests/test_supervisor_safety.py`
  - The current timeout test expects `running_actual=false` while the thread is alive.
    Update it to match the reviewed lifecycle contract.
- `tests/test_web_desire.py`
  - Add endpoint behavior for Start rollback failure, Stop timeout, and persistence
    failures.
- `tests/test_runtime_state.py`
  - Current concurrency test only proves operations do not raise. Keep it, but do not
    treat it as proof of multi-operation transactional behavior.

## Verification Evidence From Review

The repository was clean at review head `2f13bda`.

Executed in an ephemeral container based on the repository's existing built image:

```text
Full backend suite: 420 passed, 6 skipped
Targeted lifecycle suite: 37 passed
Ruff on affected lifecycle files: passed
Frontend production build: passed
git diff --check: passed
```

The passing suite does not invalidate the findings; each defect above was separately
reproduced with a focused runtime script.

## Verification Required After Fixes

Run at minimum:

```bash
python -m pytest -q \
  tests/test_runtime_state.py \
  tests/test_supervisor_autostart.py \
  tests/test_supervisor_safety.py \
  tests/test_web_desire.py \
  tests/test_web_lifespan.py

python -m pytest -q
ruff check src tests
cd frontend && npm run build
```

Also manually or programmatically verify:

1. Successful Start results in `running_actual=true` and `running_desired=true`.
2. A failed desire write during Start does not leave an active loop.
3. Successful Stop results in no live loop thread and `running_desired=false`.
4. A Stop timeout is visibly reported and blocks a second Start.
5. A desire-write failure during Stop still attempts to stop the active loop.
6. A runtime-state read failure remains visible through `/api/control/lifecycle`.

## Scope Guardrails

- Do not change trading strategy behavior.
- Do not remove the lifecycle lock or state lock ordering.
- Do not allow duplicate supervisor loop threads.
- Do not make halt, pause, resume, or application shutdown clear
  `running_desired`.
- Keep auto-start paper-only and failure-tolerant.
- Preserve default `running_desired=false` for existing/fresh installations.
