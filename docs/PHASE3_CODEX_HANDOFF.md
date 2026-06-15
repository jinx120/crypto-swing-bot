# Phase 3 — Codex Code Handoff

> **Purpose:** Self-contained brief for an external code-generation pass (Codex) running against a
> fresh clone of `jinx120/crypto-swing-bot`. It distills *exactly* what Phase 3 is, the contracts it
> must honor verbatim, what already exists (do not rebuild), and the output format required so the
> result drops straight into this project's plan/execute pipeline.
>
> **Authoritative spec (read in the clone):**
> `docs/superpowers/specs/2026-06-13-visible-autonomous-entry-design-reviewed.md` — Phase 3 is
> **§5 "Phase 3: Make outcomes durable and truthful"** plus the supporting contracts §3.2, §3.3, §4,
> §6. This handoff quotes the binding parts so Codex needn't re-derive them, but the spec wins on any
> conflict. **Treat the spec as final design — do not re-litigate it.**
>
> **Status anchor (read in the clone):** `docs/ROADMAP_STATUS.md` → NEXT ACTION. Phases 0/1/2/2.1 are
> DONE and on `master`. Phase 3 is the next unit of work.

---

## 0. What Codex should produce

Two acceptable deliverables (the human will format the plan; Codex's job is correct, reviewable code
+ tests):

1. **Primary: Phase 3 implementation code + tests**, organized by the 5 work items in §2 below, each
   as an isolated, test-backed change. Write tests first (this repo is strict TDD — see §7). Every new
   module gets a focused pytest module; every decision code and stage outcome gets a test.
2. **Optional: a task list** in this repo's plan format if Codex wants to structure its own work —
   markdown with `## Task N: <title>` headings and `- [ ] **Step ...**` checkbox steps. The human
   maintainer will reformat/validate whatever Codex returns into the canonical
   `docs/superpowers/plans/2026-06-15-...-phase-3.md` before execution, so do not over-invest in plan
   prose — invest in code correctness and test coverage.

**Do not** touch frontend dashboard work (that is Phase 5), managed-profile/probe work (Phase 4), or
lifecycle/broker hardening (Phases 1/2/2.1 — already shipped). Phase 3 is backend telemetry +
durability + health API only.

---

## 1. Current code state — build on this, do NOT rebuild

These are already implemented, tested, and live on `master`. Phase 3 consumes them; it must not
re-implement or weaken them.

| Already done (prior phases) | Where | Phase 3 relationship |
|---|---|---|
| Lifecycle truth layer: `running_desired`, `running_actual` (= thread-alive), `startup_error`, `request_start()`, `request_stop()`, `lifecycle_state()`, typed `LifecycleError`/`DesirePersistError` | `src/swingbot/supervisor.py` | `/api/health/trading` reads this surface; "desired-but-not-running = immediately unhealthy" comes straight from it |
| Durable `running_desired` persistence | `src/swingbot/runtime_state.py` (`RuntimeStateStore`, SQLite, RLock-guarded, `check_same_thread=False`) | **Pattern to copy** for the new telemetry/trade SQLite stores (same locking discipline) |
| Supervisor thread-safety: `_lifecycle_lock` then `_state_lock` RLocks, lock order lifecycle→state | `src/swingbot/supervisor.py` | New cycle-telemetry writes must respect this lock order; never acquire lifecycle while holding state |
| Broker truth (Critical 2 — FIXED): `get_position()` returns `None` only on Alpaca 404; all other `APIError` propagate | `src/swingbot/broker/alpaca.py:29` | Reconcile/decide telemetry records propagated broker errors as `reconcile: failed`, not flat |
| Auto-resume paper loop on boot via FastAPI lifespan | `src/swingbot/webmain.py`, `web.py` | Health/ready endpoints register in the same app |
| `POST /api/control/start|stop|halt|pause|resume`, `GET /api/control/lifecycle` | `src/swingbot/web.py` | Add the three `/api/health/*` routes alongside |

### Gaps Phase 3 fills (none of these exist yet — verified)

- **No** `src/swingbot/telemetry.py` (new).
- **No** `src/swingbot/trade_store.py` (new) — `TradeJournal` (`src/swingbot/journal.py:23`) is
  **in-memory only**; trades vanish on restart.
- **No** `DecisionResult` type, **no** decision codes anywhere in `src/swingbot/`.
- **No** `/api/health/*` endpoints.
- Orchestrator gates return `None`: `tick()`, `_maybe_enter()`, `_manage_open()`, `reconcile()`,
  `flatten()` in `src/swingbot/orchestrator.py` — Phase 3 makes the entry/exit/manage paths return a
  structured `DecisionResult` instead of mutating-and-returning-None.

---

## 2. Phase 3 scope — the 5 work items (spec §5 Phase 3)

> Exit criterion (spec, verbatim): *"every cycle has a terminal record; every no-entry has a stable
> reason code; restart preserves trades, markers, and the last decision."*

1. **Structured cycle/decision records with rolling retention.**
   New `src/swingbot/telemetry.py` + SQLite store. Each completed strategy cycle stores one record
   (schema in §3 below). Rolling retention keeps at least the latest 200 completed cycles per the
   reliability window (§4). Cycle telemetry is **coordinated by `PortfolioSupervisor`** (spec High 1),
   with structured results returned up from orchestrator operations — do **not** bury an imagined
   5-stage pipeline inside `Orchestrator.tick()`.

2. **Refactor orchestrator entry gates to return a structured `DecisionResult`.**
   `_maybe_enter()` / `_manage_open()` / the `tick()` path return a `DecisionResult` carrying a stable
   `decision_code`, human `decision_reason`, and `decision_details`. Codes are the API/test contract;
   reasons are free text. Add to `src/swingbot/types.py`.

3. **Order/pending/fill state + broker-confirmed position persistence (Critical 4).**
   Model `pending_order -> broker-confirmed open position`. **Stop** persisting an `OpenPosition` from
   the last candle close at submit time. Either confirm fill (status, filled qty, fill price) via a
   bounded post-submit reconciliation, or persist a pending order and promote to position only on
   broker-confirmed fill. Telemetry must distinguish `ORDER_SUBMITTED`, `ORDER_PENDING`, `ENTERED`,
   `ORDER_FAILED`. Touches `broker/alpaca.py`, `broker/base.py`, `orchestrator.py`, `types.py`.

4. **Persist trades; build journal/metrics/markers from SQLite (High 6).**
   New `src/swingbot/trade_store.py` (or extend `state.py` — spec prefers a dedicated store).
   `TradeJournal`, metrics, and chart markers are rebuilt from durable records. Closed trades, P&L,
   and markers survive restart.

5. **Add `/api/health/live`, `/api/health/ready`, `/api/health/trading` (Medium 3).**
   Three **separate** API contracts (UI may combine them; the API must not):
   - `/api/health/live` — process is serving.
   - `/api/health/ready` — required dependencies/configuration usable.
   - `/api/health/trading` — desired/running state, last cycle, stage ratios, decisions, with the
     reliability semantics in §4. In `src/swingbot/web.py`.

---

## 3. Cycle & decision record contract (spec §3.2) — honor verbatim

Each strategy cycle stores:

```text
cycle_id, strategy, started_at, completed_at, bar_ts
ingest:    ok | failed
reconcile: ok | failed
manage:    ok | failed | skipped
decide:    ok | failed | skipped
persist:   ok | failed
decision_code, decision_reason, decision_details
```

**Stable decision codes** (these are API/test contracts — store separately from human reasons;
sanitize + length-limit any exception text before persistence):

```text
PAUSED  HALTED  BROKER_POSITION_EXISTS  RISK_BLOCKED  REGIME_BLOCKED
SIGNAL_BELOW_THRESHOLD  ATR_INVALID  SIZE_ZERO  PORTFOLIO_BLOCKED
ORDER_SUBMITTED  ORDER_PENDING  ENTERED  ORDER_FAILED
MANAGED_NO_EXIT  EXIT_SUBMITTED  EXITED  ERROR
```

Stage rules: **Manage is required only when a position exists; Decide is required only when flat. A
skipped stage is not a failure.**

---

## 4. Reliability contract (spec §3.3) — honor verbatim

Over the **latest 200 completed cycles**:

- Per-stage reliability = `ok / (ok + failed)`, **excluding skipped**.
- Cycle-completion reliability = cycles where every *required* stage succeeded / completed cycles.
- Critical-stage floor = min reliability among **ingest, reconcile, persist**.
- Always show sample counts + window timestamps; **never a bare percentage**.
- A stopped-by-desire loop is `inactive` (not healthy/unhealthy).
- **A desired-but-not-running loop is immediately unhealthy, independent of the rolling score.**
  (This reads `running_desired` + `running_actual` from the supervisor lifecycle surface in §1.)

Reliability outcomes use `ok | failed | skipped`; exclude `skipped` from denominators; overall cycle
success = all required stages for that cycle succeeded (spec Medium 1).

---

## 5. Component boundaries (spec §4) — where code goes

| Responsibility | Files |
|---|---|
| Cycle/decision telemetry | **new** `src/swingbot/telemetry.py`, `supervisor.py`, `orchestrator.py` |
| Order/pending/fill + broker-confirmed position | `broker/alpaca.py`, `broker/base.py`, `orchestrator.py`, `types.py` |
| Durable trades | **new** `src/swingbot/trade_store.py` (preferred) or `state.py`, `supervisor.py` |
| Health API | `src/swingbot/web.py` |

Prefer dedicated stores/modules over expanding `profiles.py`/`state.py` into unrelated concerns.
Copy the `RuntimeStateStore` SQLite + RLock pattern (`runtime_state.py`) for new stores.

---

## 6. Freshness (spec Medium 2) — applies to telemetry timestamps

Normalize to **closed bars**, record latest closed-bar timestamp, exclude any in-progress bar, and
use a documented tolerance `expected_close + provider_grace` (not a strict "older than one
timeframe"). Test boundary times.

---

## 7. Test matrix (spec §6) + house rules

**TDD is mandatory in this repo — write the failing test first, then the implementation.**

Required Phase-3-relevant cases (spec §6):

| Area | Cases |
|---|---|
| Orders | rejected, pending, partial fill, filled, restart while pending, duplicate prevention |
| Telemetry | every decision code, stage exception, skipped denominator, rolling retention |
| Freshness | empty, stale, provider-grace boundary, in-progress bar excluded, fresh closed bar |
| Persistence | last decision, position, pending order, trades, metrics across restart |
| Broker truth | confirmed flat, confirmed position, not-found, auth error, timeout, rate limit |

Use a **deterministic fake broker + fake clock** for the integration suite (no live Alpaca). Keep real
Alpaca paper acceptance opt-in and clearly labeled.

**Regression gate (must stay green):**
```bash
.venv/bin/python -m pytest -q      # baseline before Phase 3: 431 passed, 6 skipped
cd frontend && npm run build       # only if frontend touched (Phase 3 shouldn't)
```

**Environment / standing rules (carry into the clone):**
- Python venv is `.venv/bin/python` — plain `python`/`pytest` are NOT on PATH.
- graphify CLI: `python3 -m graphify update .` after code changes (AST-only, no API cost).
- App runs in Docker (`:8000`); rebuild = `docker compose build swingbot && docker compose up -d swingbot`.
  (This is the maintainer's local-execution concern; Codex just produces code + tests.)
- Work targets `master`; scope each change to its task's files. The working tree may carry unrelated
  uncommitted FVG/presets/graphify work that must stay untouched.

---

## 8. Phase 3 success criteria (subset of spec §7 relevant here)

5. Every desired cycle produces durable stage outcomes and a stable terminal decision code.
6. Orders and positions shown are **broker-confirmed**, not inferred from submission.
7. Trades, metrics, markers, and last decisions survive restart.
8. Reliability reports sample counts, skipped semantics, and the desired-but-not-running failure.
