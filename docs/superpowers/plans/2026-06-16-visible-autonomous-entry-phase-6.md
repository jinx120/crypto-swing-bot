# Visible Autonomous Entry — Phase 6: Live acceptance

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the full "visible autonomous entry" sub-project against a real paper account by running the spec §Phase 6 acceptance procedure end-to-end, backed by a deterministic, Alpaca-free harness that mirrors the live wiring and a repeatable, recorded live runbook.

**Architecture:** Phase 6 ships almost no new product code — the behavior was built in Phases 1–5. It adds (A) one composed acceptance integration test that wires a supervisor exactly the way `webmain.py` does (managed reconcile + probe marker + persisted desire + `auto_start_if_desired`) and asserts the seven runbook outcomes deterministically using the existing fake broker/market; (B) a `scripts/backup-data-dir.sh` data-dir backup tool (spec step 1); and (C) `docs/PHASE6_LIVE_ACCEPTANCE.md`, an exact-command runbook that an operator executes against the live container in **real Alpaca paper mode** and records results into. The deterministic test is the *reproducible support*; the live run is the *authoritative* acceptance, kept opt-in and clearly labeled per spec §6.

**Tech Stack:** Python 3.11, pytest, ruff, Docker Compose, FastAPI, Alpaca paper API. No frontend changes (Phase 5 already shipped the dashboard).

---

## Context for a cold code-gen agent

You are implementing Phase 6 (the final phase) of the "visible autonomous entry" roadmap for `crypto-swing-bot`. You may have **zero prior context**. Read this section before touching anything.

### House rules (non-negotiable)
- **Python interpreter:** `.venv/bin/python` (plain `python`/`pytest` are NOT on PATH). Run tests with `.venv/bin/python -m pytest -q`.
- **TDD for code:** for every code change write the failing test first, watch it fail, then implement. Commit per task.
- **Lint:** `.venv/bin/ruff check src/ tests/` must be clean before each commit (ruff is at `.venv/bin/ruff`, not on PATH).
- **Scope discipline:** `git add` only the files the current task names. The working tree carries **unrelated uncommitted FVG/presets/graphify work — leave it untouched.** Never `git add -A`.
- **Docker rebuild policy (standing rule):** any code change requires `docker compose build swingbot && docker compose up -d swingbot`. On this host the compose file pins `runtime: nvidia`, which the daemon lacks; if `up` fails on that, use a temporary local override `runtime: runc` (do not commit it). This is pre-authorized; do not ask.
- **No new frontend.** Phase 5 finished the dashboard. Phase 6 only *observes* it.

### Current code state (what Phases 1–5 already built — rely on it, do not rewrite)
- `src/swingbot/webmain.py` is the live entrypoint. It already wires: `reconcile_managed_profiles(profiles, enable_probe=<SWINGBOT_ENABLE_PAPER_PROBE=="1">, mode="paper", backup_dir=DATA_DIR/backups)` as the supervisor `reconcile` hook; a `ProbeMarkerStore(DATA_DIR/probe_markers.db)`; a `RuntimeStateStore(DATA_DIR/swingbot.db)` for persisted desire; and a FastAPI lifespan that calls `supervisor.auto_start_if_desired()` after the poller starts. Relevant env vars: `SWINGBOT_DATA_DIR` (default `~/.swingbot`), `SWINGBOT_PORT` (8000), `SWINGBOT_ENABLE_PAPER_PROBE` (`"1"` to enable the probe).
- `src/swingbot/supervisor.py` — `PortfolioSupervisor`. Key methods used by this plan:
  - `__init__(profiles, creds, state_db, market=None, broker=None, mode="paper", runtime_state=None, reconcile=None, probe_marker=None, ...)`. Passing `broker=<fake>` bypasses Alpaca entirely (the only seam tests use).
  - `build()` — runs the `reconcile` hook, then builds `self._strategies` from armed profiles.
  - `request_start()` / `request_stop()` — serialized lifecycle transitions that persist desire; `auto_start_if_desired()` — paper-only, failure-tolerant resume used by the lifespan.
  - `tick_all(now=None)` — one strategy cycle for every armed strategy: reconciles pending orders against the broker, promotes broker-confirmed positions, decides, persists telemetry. Probe entry is gated by `_probe_suppressed(name, position_exists)` (a completed, flat probe yields terminal `DecisionCode.PROBE_COMPLETE` and never re-enters; a probe still holding a position keeps ticking so it can exit).
  - `note_managed_decision(name, decision)` — marks a probe complete (durable) the first time it returns a terminal `ENTERED`.
  - `lifecycle_state()` → `{mode, running_flag, thread_alive, running_actual, running_desired, running_desired_error, paused, halted, startup_error}`.
  - `readiness()` → `{ready: bool, checks: {credentials, armed_strategies, lifecycle_desire_readable, completed_cycle_while_desired, latest_critical_stages}}`. **Local only — never calls the broker/network.**
  - `trading_health()` → `{status ∈ {active,inactive,unhealthy}, lifecycle, last_cycle, last_decisions_by_strategy, reliability}`.
  - `status()` → broker-confirmed `portfolio` + per-strategy `position`/`pending_orders`/`kind`/`label`/`probe_complete` (Phase 5 enrichment). `self._store` is the state/order/trade store; `self._telemetry` the cycle store; `self._market` the local market cache.
- `src/swingbot/managed_profiles.py` — `MANAGED_PROFILE_NAMES = {"btc_trend","eth_trend","paper_probe"}`; `managed_definitions(enable_probe: bool) -> dict[name, profile_dict]`; `reconcile_managed_profiles(profiles, *, enable_probe, mode, backup_dir)` (versioned, backs up before write, never deletes/overwrites *user* profiles).
- `src/swingbot/probe_marker.py` — `ProbeMarkerStore(path)` with `.is_complete(name) -> bool` and `.mark_complete(name)`.
- `src/swingbot/types.py` — `DecisionCode` (incl. `ENTERED`, `PROBE_COMPLETE`), `DecisionResult(code, reason)`, `OrderSide`, `OrderStatus`, `BrokerOrder`, `OpenPosition`, `PendingOrder`, `Regime`, `Side`, `ExitReason`.

### Existing deterministic guarantees you should NOT re-test (DRY — they already pass)
`tests/test_phase3_integration.py` already pins, with a fake broker + fake clock: restart-with-pending-buy submits no duplicate and promotes exactly one position; a confirmed exit survives restart in journal/metrics/markers; broker errors record a failed reconcile **without clearing the position**; reliability uses exactly the latest 200 completed cycles; desired-but-not-running is unhealthy. `tests/test_supervisor_managed.py` pins probe fire-once suppression, label/`probe_complete` status, pending-order status, and unrealized P&L. **Do not duplicate these.** Phase 6's test *composes* them into the one live-shaped scenario the runbook walks.

### Test fixtures to reuse (import them; do not re-define)
From `tests/test_supervisor.py`: `T0` (a fixed `datetime`), `_bars(symbol_base=100.0, n=120)`, `FakeMarket({"BTC/USD": _bars(...)})`, `FakeBroker` (minimal: `get_account`, `get_position`, `get_order`, `submit_market_buy/sell`; **no** injectable errors — for the failure task subclass it). From `tests/test_supervisor_managed.py`: the `_probe_supervisor(tmp_path, mode="paper")` helper builds a supervisor whose only armed strategy is the managed `paper_probe` (returns `(sup, broker, marker)`). From `tests/test_supervisor_telemetry.py`: `_position(symbol="BTC/USD")` builds an `OpenPosition`.

### Success criteria (Phase 6 is done when)
1. `tests/test_phase6_acceptance.py` exists and passes: it builds a supervisor wired like `webmain` (managed reconcile + probe marker + persisted desire) and asserts, deterministically, the runbook outcomes for steps 3–7 (auto-resume without Start; fresh cycle records + terminal decision codes; probe fill→broker-confirmed position→durable completion marker; restart→no duplicate probe/order; broker failure→not-ready/unhealthy without clearing the position or duplicating orders).
2. `scripts/backup-data-dir.sh` exists, backs the data dir up to a timestamped tarball, and is verified by a real run.
3. `docs/PHASE6_LIVE_ACCEPTANCE.md` exists with exact commands and an explicit pass/fail check per spec step (1–7).
4. The live runbook has been **executed against the container in paper mode** and its results (observed values, pass/fail) recorded into `docs/PHASE6_LIVE_ACCEPTANCE.md`.
5. Full gate green: `.venv/bin/python -m pytest -q` (expect prior `556 passed, 6 skipped` plus the new acceptance tests) and `.venv/bin/ruff check src/ tests/` clean. `cd frontend && npm run build` green (frontend untouched, but the gate runs it).
6. `docs/ROADMAP_STATUS.md` updated: Phase 6 done; sub-project "visible autonomous entry" complete.

### Spec
Authoritative: `docs/superpowers/specs/2026-06-13-visible-autonomous-entry-design-reviewed.md` §"Phase 6: Live acceptance" (steps 1–7) and §7 "Revised success criteria" (10 items). The runbook in Part C maps 1:1 to those seven steps.

---

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `tests/test_phase6_acceptance.py` | Create | Deterministic, Alpaca-free acceptance harness composing the live-shaped scenario (Tasks 1–4). |
| `scripts/backup-data-dir.sh` | Create | Timestamped tarball backup of `$SWINGBOT_DATA_DIR` before a live acceptance run (Task 5). |
| `docs/PHASE6_LIVE_ACCEPTANCE.md` | Create | Exact-command live runbook + recorded results (Tasks 6–7). |
| `docs/ROADMAP_STATUS.md` | Modify | Mark Phase 6 / sub-project done (Task 8). |

No `src/` changes are expected. If a runbook step uncovers a real defect, stop and open a focused fix as its own task before continuing — do not patch around it in the test.

---

## Task 1: Acceptance harness — auto-resume without Start + truthful readiness

**Files:**
- Create: `tests/test_phase6_acceptance.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_phase6_acceptance.py
"""Phase 6 deterministic acceptance harness.

Mirrors the live webmain wiring (managed reconcile + probe marker + persisted
desire + auto_start_if_desired) with a fake broker/market, and composes the
spec §Phase 6 runbook outcomes into one place. The AUTHORITATIVE acceptance is
the live paper run recorded in docs/PHASE6_LIVE_ACCEPTANCE.md; this suite is the
reproducible, Alpaca-free support for it.
"""
from datetime import timedelta

import pytest

from swingbot.managed_profiles import reconcile_managed_profiles
from swingbot.probe_marker import ProbeMarkerStore
from swingbot.profiles import ProfileStore
from swingbot.runtime_state import RuntimeStateStore
from swingbot.supervisor import PortfolioSupervisor
from swingbot.types import (
    BrokerOrder, DecisionCode, DecisionResult, OrderSide, OrderStatus,
    PendingOrder, Regime,
)
from tests.test_supervisor import FakeBroker, FakeMarket, T0, _bars
from tests.test_supervisor_telemetry import _position


def _wire(tmp_path, *, enable_probe, broker=None, desired=False):
    """Build a supervisor exactly the way webmain.py does, over a shared data dir."""
    db = str(tmp_path / "swingbot.db")
    profiles = ProfileStore(db)
    market = FakeMarket({"BTC/USD": _bars(100.0), "ETH/USD": _bars(100.0)})
    broker = broker if broker is not None else FakeBroker()
    marker = ProbeMarkerStore(str(tmp_path / "probe_markers.db"))
    runtime_state = RuntimeStateStore(db)
    if desired:
        runtime_state.set_running_desired(True)   # verified API (runtime_state.py:32)

    def _reconcile():
        reconcile_managed_profiles(
            profiles, enable_probe=enable_probe, mode="paper",
            backup_dir=str(tmp_path / "backups"),
        )

    sup = PortfolioSupervisor(
        profiles=profiles, creds=None, state_db=db, market=market, broker=broker,
        mode="paper", runtime_state=runtime_state, reconcile=_reconcile,
        probe_marker=marker,
    )
    sup.build()
    return sup, broker, marker, profiles


def test_managed_canvas_seeds_and_auto_resumes_without_start(tmp_path):
    # First boot: operator pressed Start once, desire persisted.
    sup, broker, _marker, profiles = _wire(tmp_path, enable_probe=False, desired=True)
    armed = set(profiles.list_armed())
    assert {"btc_trend", "eth_trend"} <= armed          # managed canvas seeded
    assert "paper_probe" not in armed                   # probe off by default

    # Container restart: a brand-new supervisor over the SAME data dir, no Start press.
    sup2, _b2, _m2, _p2 = _wire(tmp_path, enable_probe=False, desired=True)
    sup2.auto_start_if_desired()
    life = sup2.lifecycle_state()
    assert life["running_desired"] is True
    assert life["running_actual"] is True               # resumed with no button press
    assert life["startup_error"] is None
    sup2.request_stop()
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_phase6_acceptance.py -q`
Expected: FAIL on a genuine assertion or missing behavior — **not** a typo. The desire setter is `set_running_desired(bool)` (verified, `runtime_state.py:32`) and `save_position`/`load_position` take a `strategy=` kwarg (verified, `state.py:60`/`74`); those are baked into the code above. If anything else mismatches, resolve it against real source before proceeding — do not invent a name.

- [ ] **Step 3: Make it pass**

There is no product code to add — this composes shipped behavior. Resolve the desire-setter name from Step 2 so `_wire` persists desire correctly, and confirm `reconcile_managed_profiles` seeds `btc_trend`/`eth_trend` (it does; see `tests/test_managed_reconcile.py`). If `auto_start_if_desired()` does not flip `running_actual` true with a fake broker, read its body — it is paper-only and failure-tolerant; ensure `mode="paper"` and a non-None `broker` are passed (they are).

- [ ] **Step 4: Run it and confirm it passes**

Run: `.venv/bin/python -m pytest tests/test_phase6_acceptance.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check tests/test_phase6_acceptance.py
git add tests/test_phase6_acceptance.py
git commit -m "test(phase6): acceptance harness — managed canvas seeds + auto-resume without Start"
```

---

## Task 2: Acceptance harness — probe fill → broker-confirmed position → durable completion marker + cycle record

**Files:**
- Modify: `tests/test_phase6_acceptance.py`

This composes three individually-tested building blocks into the runbook's step 5: a probe entry confirmed by the broker, promoted to a broker-confirmed position, with a durable completion marker and a telemetry cycle record carrying a terminal decision code and a bar timestamp.

- [ ] **Step 1: Write the failing test**

```python
def test_probe_entry_confirmed_promotes_position_marks_complete_and_records_cycle(tmp_path):
    broker = FakeBroker()
    sup, broker, marker, profiles = _wire(tmp_path, enable_probe=True, broker=broker)
    assert "paper_probe" in set(profiles.list_armed())   # probe armed when enabled

    # A probe entry was submitted last cycle: a pending buy is on the books.
    pending = PendingOrder(
        client_order_id="probe-coid",
        broker_order_id="probe-coid",
        symbol="BTC/USD",
        side=OrderSide.BUY,
        submitted_at=T0,
        requested_qty=1.0,
        stop=None, tp=None, max_hold_until=None,
        score_at_entry=1.0, regime_at_entry=Regime.TREND,
        exit_reason=None, observed_exit_price=None,
    )
    sup._store.save_pending_order(pending, strategy="paper_probe")

    # Broker confirms the fill and reports the resulting position (broker truth).
    broker.order = BrokerOrder(
        "probe-1", "BTC/USD", OrderSide.BUY, OrderStatus.FILLED,
        1.0, 1.0, 100.0, "probe-coid",
    )
    broker.positions["BTC/USD"] = {
        "symbol": "BTC/USD", "qty": 1.0, "avg_entry_price": 100.0, "market_value": 100.0,
    }

    sup.tick_all(T0)

    # Broker-confirmed position is now durable and visible.
    st = sup.status()
    probe_row = next(s for s in st["strategies"] if s["name"] == "paper_probe")
    assert probe_row["position"] is not None
    assert probe_row["position"]["qty"] == 1.0

    # The probe is durably marked complete (fire-once promise).
    sup.note_managed_decision("paper_probe", DecisionResult(DecisionCode.ENTERED, "probe filled"))
    assert marker.is_complete("paper_probe") is True

    # A cycle record exists with a bar timestamp and a stable terminal decision code.
    row = sup._telemetry.recent(strategy="paper_probe")[0]
    assert row.bar_ts is not None
    assert isinstance(row.decision_code, DecisionCode)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_phase6_acceptance.py::test_probe_entry_confirmed_promotes_position_marks_complete_and_records_cycle -q`
Expected: FAIL. Likely culprits to resolve from the real source (do not guess): the `PendingOrder` field list (confirm against `src/swingbot/types.py`), the `save_pending_order` signature, and how `status()` nests the position. Fix the test to match real signatures — this is a composition test, so all the machinery already exists.

- [ ] **Step 3: Make it pass**

No product code. Align the `PendingOrder` construction, `save_pending_order(..., strategy=...)`, and the `status()`/`recent()` access paths with the real APIs (cross-check `tests/test_phase3_integration.py` `_pending_sell` and `tests/test_supervisor_managed.py` for exact shapes). If `tick_all` does not promote the position, verify the broker fake returns the `FILLED` order from `get_order(client_order_id=...)` and the position from `get_position("BTC/USD")` (the shipped `FakeBroker` does both).

- [ ] **Step 4: Run it and confirm it passes**

Run: `.venv/bin/python -m pytest tests/test_phase6_acceptance.py -q`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check tests/test_phase6_acceptance.py
git add tests/test_phase6_acceptance.py
git commit -m "test(phase6): probe fill promotes broker-confirmed position, marks complete, records cycle"
```

---

## Task 3: Acceptance harness — restart does not duplicate the probe/order

**Files:**
- Modify: `tests/test_phase6_acceptance.py`

Runbook step 6: after the probe has fired and (in this scenario) gone flat, a fresh supervisor over the same data dir must not re-enter — the completed-probe suppression yields `PROBE_COMPLETE` and places no new order. (A probe still holding a position keeps managing it; that branch is covered by `test_completed_probe_still_manages_open_position` — do not duplicate it.)

- [ ] **Step 1: Write the failing test**

```python
def test_restart_does_not_reenter_completed_flat_probe(tmp_path):
    # Boot 1: probe enabled, marked complete, and flat (no position).
    sup, broker, marker, _profiles = _wire(tmp_path, enable_probe=True)
    marker.mark_complete("paper_probe")

    # Boot 2: container restart — fresh supervisor, SAME data dir (same swingbot.db +
    # probe_markers.db that _wire created under tmp_path). The state store has no public
    # path attribute, so reuse the known tmp_path filenames directly.
    sup2 = PortfolioSupervisor(
        profiles=sup.profiles, creds=None, state_db=str(tmp_path / "swingbot.db"),
        market=sup._market, broker=broker, mode="paper",
        probe_marker=ProbeMarkerStore(str(tmp_path / "probe_markers.db")),
    )
    sup2.build()
    before = list(broker.buys)

    sup2.tick_all(T0)

    assert broker.buys == before                         # no duplicate probe order
    row = sup2._telemetry.recent(strategy="paper_probe")[0]
    assert row.decision_code is DecisionCode.PROBE_COMPLETE
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_phase6_acceptance.py::test_restart_does_not_reenter_completed_flat_probe -q`
Expected: FAIL on a genuine assertion (e.g. the second boot's suppression/telemetry). The state store exposes no public path attribute (verified), so Boot 2 reuses the known `tmp_path` filenames directly — the point is a *fresh object graph over the same on-disk files*. If `_probe_suppressed` does not fire, confirm the same `probe_markers.db` path is reused so `is_complete("paper_probe")` reads true across the boundary.

- [ ] **Step 3: Make it pass**

No product code. Make Boot 2 genuinely reuse the on-disk state + probe marker from Boot 1. The suppression (`_probe_suppressed` → `PROBE_COMPLETE`) is shipped and unit-tested; this only proves it survives a process boundary.

- [ ] **Step 4: Run it and confirm it passes**

Run: `.venv/bin/python -m pytest tests/test_phase6_acceptance.py -q`
Expected: PASS (three tests).

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check tests/test_phase6_acceptance.py
git add tests/test_phase6_acceptance.py
git commit -m "test(phase6): restart does not re-enter a completed flat probe"
```

---

## Task 4: Acceptance harness — broker/network failure stays truthful (no false-flat, no duplicate orders)

**Files:**
- Modify: `tests/test_phase6_acceptance.py`

Runbook step 7: a credential/network failure must keep the UI surfaces available and truthful — readiness/health reflect the failure, the open position is **not** cleared, and no duplicate order is placed. The shipped `FakeBroker` has no error injection, so subclass it.

> **Real defect found & fixed (issue #2).** As the plan anticipated, the Task 4 scenario exposed a genuine `src/` gap: `tick_all` fetched the broker account *outside* the per-strategy try/except, so a total broker outage raised straight out of the cycle (no telemetry, no truthful health). Fixed as its own focused TDD task in `1553eba` (`fix(supervisor): keep tick_all truthful when broker account fetch fails`): the account fetch is now wrapped — on failure the daily reset is skipped, every strategy's cycle is recorded as a failed broker cycle (no entries, position preserved, never read as flat), and the last-known-good summary is retained. Regression-guarded by `tests/test_phase3_integration.py::test_account_fetch_failure_records_failed_cycle_without_clearing_or_duplicating`. This acceptance test then passes with no further product change.

- [x] **Step 1: Write the failing test**

```python
class FailingBroker(FakeBroker):
    """A broker whose queries raise — simulates expired creds / network loss."""
    def get_account(self):
        raise ConnectionError("alpaca unreachable")
    def get_position(self, s):
        raise ConnectionError("alpaca unreachable")
    def get_order(self, order_id=None, client_order_id=None):
        raise ConnectionError("alpaca unreachable")


def test_broker_failure_does_not_false_flat_or_duplicate(tmp_path):
    broker = FailingBroker()
    sup, broker, _marker, _profiles = _wire(tmp_path, enable_probe=False, broker=broker)

    # A broker-confirmed position is already on the books for a managed strategy.
    sup._store.save_position(_position(), strategy="btc_trend")
    before_buys = list(broker.buys)

    # A cycle under total broker failure must not raise out of tick_all...
    sup.tick_all(T0)

    # ...the position is NOT cleared by an error being mistaken for "flat"...
    assert sup._store.load_position("btc_trend") is not None
    # ...and no order was placed off the back of a failed reconcile.
    assert broker.buys == before_buys

    # readiness()/trading_health() are local-only and stay answerable (never raise).
    ready = sup.readiness()
    assert isinstance(ready["ready"], bool)
    health = sup.trading_health()
    assert health["status"] in {"active", "inactive", "unhealthy"}
```

- [x] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest tests/test_phase6_acceptance.py::test_broker_failure_does_not_false_flat_or_duplicate -q`
Expected: FAIL. Resolve real method names: confirm `save_position`/`load_position` signatures.

```bash
grep -n "def save_position\|def load_position\|def load_all_positions" src/swingbot/state.py
```

If the loader is named differently (e.g. `get_position(strategy=...)` or `load_all_positions()`), adjust the assertion to read the same position back by strategy. Do not change the *intent*: position present after a failed cycle.

- [x] **Step 3: Make it pass**

Expected to pass with **no product change** — `tests/test_phase3_integration.py::test_broker_errors_record_failed_reconcile_without_clearing_position` already proves the broker-error-≠-flat contract. If `tick_all` instead *raises* out under a fully-failing broker, that is a real Phase 6 finding: **stop, do not swallow it in the test** — open a separate hardening task (mirroring the Phase 3 reconcile try/except) and reference it here. The acceptance test asserts the truthful-failure contract; it must not paper over a regression.

- [x] **Step 4: Run it and confirm it passes**

Run: `.venv/bin/python -m pytest tests/test_phase6_acceptance.py -q`
Expected: PASS (four tests).

- [x] **Step 5: Commit**

```bash
.venv/bin/ruff check tests/test_phase6_acceptance.py
git add tests/test_phase6_acceptance.py
git commit -m "test(phase6): broker failure stays truthful — no false-flat, no duplicate orders"
```

---

## Task 5: Data-dir backup script (spec step 1)

**Files:**
- Create: `scripts/backup-data-dir.sh`

Spec step 1 requires backing up the data directory before a live acceptance run. There is no bash test runner in this project; verify by running it.

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# Back up the swingbot data directory to a timestamped tarball before a live
# acceptance run (spec §Phase 6 step 1). Read-only with respect to the source.
#
# Usage: scripts/backup-data-dir.sh [DATA_DIR] [DEST_DIR]
#   DATA_DIR  defaults to $SWINGBOT_DATA_DIR or ~/.swingbot
#   DEST_DIR  defaults to $DATA_DIR/backups
set -euo pipefail

DATA_DIR="${1:-${SWINGBOT_DATA_DIR:-$HOME/.swingbot}}"
DEST_DIR="${2:-$DATA_DIR/backups}"

if [[ ! -d "$DATA_DIR" ]]; then
  echo "error: data dir not found: $DATA_DIR" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$DEST_DIR/swingbot-data-$STAMP.tar.gz"

# Exclude the backups dir itself to avoid recursive growth.
tar --exclude="$(basename "$DEST_DIR")" -czf "$ARCHIVE" -C "$(dirname "$DATA_DIR")" "$(basename "$DATA_DIR")"

echo "backed up $DATA_DIR -> $ARCHIVE"
ls -lh "$ARCHIVE"
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/backup-data-dir.sh
```

- [ ] **Step 3: Verify with a real run against a throwaway dir**

```bash
mkdir -p /tmp/phase6-bk/sub && echo hi > /tmp/phase6-bk/sub/x.txt
scripts/backup-data-dir.sh /tmp/phase6-bk /tmp/phase6-bk-out
tar -tzf /tmp/phase6-bk-out/swingbot-data-*.tar.gz
```

Expected: prints `backed up ... -> ...tar.gz`, and the tar listing shows `phase6-bk/sub/x.txt`. Confirm a second run produces a *distinct* timestamped file (run it twice; two archives present). Clean up: `rm -rf /tmp/phase6-bk /tmp/phase6-bk-out`.

- [ ] **Step 4: Commit**

```bash
git add scripts/backup-data-dir.sh
git commit -m "feat(phase6): data-dir backup script for live acceptance"
```

---

## Task 6: Write the live acceptance runbook (spec steps 1–7)

**Files:**
- Create: `docs/PHASE6_LIVE_ACCEPTANCE.md`

This is the **authoritative** acceptance artifact. It must contain exact commands and an explicit pass/fail check per spec step. Leave the "Observed" / "Result" cells empty — Task 7 fills them from a real run.

- [ ] **Step 1: Write the runbook**

````markdown
# Phase 6 — Live Acceptance Runbook (real Alpaca paper)

> **OPT-IN, real-money-adjacent.** This drives the live container against a **real Alpaca
> paper account**. Run only against paper. Probe steps place a real (paper) order. Back up
> first (step 1). Fill the **Observed** and **Result** columns as you go; this file is the
> recorded acceptance evidence referenced by `docs/ROADMAP_STATUS.md`.

**Preconditions**
- Container builds/runs on `:8000` (`docker compose build swingbot && docker compose up -d swingbot`;
  if the daemon lacks `runtime: nvidia`, use a temporary `runtime: runc` override, not committed).
- Real Alpaca **paper** credentials are configured in `~/.swingbot/credentials.json`.
- `TOKEN=$(cat ~/.swingbot/token)` for authenticated calls.
- Helper: `Q() { curl -fsS -H "Authorization: Bearer $TOKEN" "http://localhost:8000$1"; }`

| # | Spec step | Command(s) | Pass check | Observed | Result |
|---|-----------|------------|-----------|----------|--------|
| 1 | Back up data dir | `scripts/backup-data-dir.sh` | Prints a new `swingbot-data-<stamp>.tar.gz`; file exists | | |
| 2 | Start from managed-canvas/probe config | Set `SWINGBOT_ENABLE_PAPER_PROBE=1` in the compose env; `docker compose up -d swingbot` | `Q /api/strategies` lists `btc_trend`,`eth_trend` (kind=strategy) and `paper_probe` (kind=probe) | | |
| 3 | Rebuild/restart **without** pressing Start | (ensure desire already true from a prior Start, or press Start once, then) `docker compose build swingbot && docker compose up -d swingbot` | `Q /api/control/lifecycle` → `running_desired:true`, `running_actual:true`, `startup_error:null` (no Start press this boot) | | |
| 4 | Verify desired/actual, fresh bars, cycles, decisions | `Q /api/health/trading` | `status` ∈ {active,unhealthy}; `last_cycle.bar_ts` is a recent closed bar; `last_decisions_by_strategy` has a code+reason per armed strategy; `reliability` shows sample counts + window | | |
| 5 | Probe: confirmed fill, durable position, marker, chart marker | watch `Q /api/state` until the probe enters; cross-check Alpaca paper dashboard | `paper_probe` shows a broker-confirmed `position` (qty>0); `probe_complete:true`; an entry marker renders on the probe chart in the UI; position survives a page reload | | |
| 6 | Restart → no duplicate probe/order, position managed | `docker compose up -d swingbot` (recreate); `Q /api/state` | No second probe order on the Alpaca paper account; probe `probe_complete` still true; any open position still present and managed | | |
| 7 | Credential/network failure → UI stays available, truthful, no false-flat | `mv ~/.swingbot/credentials.json ~/.swingbot/credentials.json.bak` then `docker compose up -d swingbot`; `Q /api/health/ready`; `Q /api/state`; then restore: `mv ~/.swingbot/credentials.json.bak ~/.swingbot/credentials.json && docker compose up -d swingbot` | UI/endpoints still respond (no 500 storm); `/api/health/ready` → not ready with a credentials/reconcile reason; previously-open positions are **not** cleared to flat; **no** duplicate orders appear on Alpaca | | |

**Post-run**
- Restore credentials and confirm `running_actual:true`, `startup_error:null` again.
- Decide whether to leave the probe enabled or set `SWINGBOT_ENABLE_PAPER_PROBE` back to unset.
- Record overall PASS/FAIL and the date below.

**Acceptance result:** _<PASS/FAIL — date — operator>_
````

- [ ] **Step 2: Sanity-check the doc**

Confirm every spec §Phase 6 step (1–7) has a row and a concrete pass check. No "TBD"/"verify appropriately" — each check names the exact field/observation.

- [ ] **Step 3: Commit**

```bash
git add docs/PHASE6_LIVE_ACCEPTANCE.md
git commit -m "docs(phase6): live acceptance runbook (spec steps 1-7)"
```

---

## Task 7: Execute the live acceptance and record results

**Files:**
- Modify: `docs/PHASE6_LIVE_ACCEPTANCE.md` (fill Observed/Result + final verdict)

> **Operator task — requires the running container and real Alpaca paper creds.** Standing
> authorization covers the Docker rebuild. The probe steps place a real paper order, so this
> step is explicitly opt-in: if real paper creds are not available in this environment, mark
> steps 5–6 **DEFERRED (no live creds)**, complete steps 1–4 and 7 (which need no fill), and
> say so plainly in the verdict — do not fabricate fills.

- [ ] **Step 1: Back up and bring up the probe-enabled container**

Run runbook steps 1–2. Record the backup filename and the `/api/strategies` output.

- [ ] **Step 2: Auto-resume check (no Start press)**

Run runbook step 3. Paste the `/api/control/lifecycle` JSON into the Observed cell; mark PASS only if `running_actual:true` with no Start this boot.

- [ ] **Step 3: Truthful cycles + decisions**

Run runbook step 4. Record `status`, `last_cycle.bar_ts`, the per-strategy decision codes/reasons, and the reliability counts/window.

- [ ] **Step 4: Probe fill + restart no-duplicate (steps 5–6)**

If live creds present: drive runbook steps 5–6; cross-check the Alpaca paper dashboard for exactly one probe order; record `probe_complete`, the position, and the marker. Otherwise mark DEFERRED as above.

- [ ] **Step 5: Failure injection (step 7)**

Run runbook step 7: remove creds, restart, confirm endpoints still answer and `/api/health/ready` reports not-ready with a credential/reconcile reason and **no** position cleared / no duplicate order; then **restore creds** and confirm recovery. Record both.

- [ ] **Step 6: Write the verdict + commit**

Fill the **Acceptance result** line (PASS/FAIL/PARTIAL + date + which steps deferred and why).

```bash
git add docs/PHASE6_LIVE_ACCEPTANCE.md
git commit -m "docs(phase6): record live acceptance run results"
```

---

## Task 8: Final regression gate + roadmap close-out

**Files:**
- Modify: `docs/ROADMAP_STATUS.md`

- [ ] **Step 1: Full gate**

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src/ tests/
cd frontend && npm run build && cd ..
```

Expected: pytest green (prior `556 passed, 6 skipped` plus the 4 new acceptance tests — i.e. `560 passed, 6 skipped`, adjust if the baseline moved); ruff clean; frontend build succeeds.

- [ ] **Step 2: Rebuild/restart the live container (standing policy)**

```bash
docker compose build swingbot && docker compose up -d swingbot
```

(Use the `runtime: runc` override if the daemon lacks `runtime: nvidia`.) Confirm `:8000` answers `/api/health/ready`.

- [ ] **Step 3: Update `docs/ROADMAP_STATUS.md`**

- Change **NEXT ACTION** away from "Phase 6 (live acceptance)" to a one-line statement that the **"visible autonomous entry" sub-project is COMPLETE** (Phases 0–6 done), pointing at `docs/PHASE6_LIVE_ACCEPTANCE.md` for the recorded evidence and noting any DEFERRED steps and the new test count.
- Add a Phase 6 paragraph mirroring the prior phase entries: plan path, the 4 acceptance tests + backup script + runbook, the gate numbers, and the live-run verdict.
- If steps 5–6 were deferred for lack of live creds, state the exact remaining manual action so a future session can finish it.

- [ ] **Step 4: Commit**

```bash
git add docs/ROADMAP_STATUS.md
git commit -m "docs(phase6): close out visible-autonomous-entry — Phase 6 acceptance done"
```

- [ ] **Step 5: (optional) Update memory**

If the live run surfaced anything non-obvious (a real failure-path defect, an Alpaca paper quirk), add/update a memory file under `~/.claude/projects/-home-redji/memory/` and its `MEMORY.md` line. Do not record what the plan/roadmap already captures.

---

## Self-review notes (author)

- **Spec coverage:** step 1 → Task 5 + runbook row 1; step 2 → runbook row 2; steps 3–4 → Task 1 + runbook rows 3–4; step 5 → Task 2 + runbook row 5; step 6 → Task 3 + runbook row 6; step 7 → Task 4 + runbook row 7. Success criteria §7 #1 (Task 1), #2 (Task 3/4 manage-not-abandon + runbook 7), #3 (Task 4 + runbook 7), #4 (covered by existing concurrency tests — not re-tested, DRY), #5 (Task 2 cycle record), #6 (Task 2 broker-confirmed), #7 (existing phase3 tests + runbook 6), #8 (runbook 4 reliability), #9 (managed reconcile preserves user profiles — `test_managed_reconcile.py`, DRY), #10 (probe opt-in — Task 2 enable flag + runbook gating).
- **No new product code is planned.** Any `src/` change means a runbook step found a real defect — that is a *finding*, handled as its own task, never hidden in a test (called out explicitly in Tasks 3 §3 and 4 §3).
- **Name-resolution discipline:** Tasks 1–4 each include a `grep` to resolve the few API names (`RuntimeStateStore` desire setter, store path, `save/load_position` signatures) against real source rather than guessing — because this clone is the source of truth and those are the only uncertain seams.
````
