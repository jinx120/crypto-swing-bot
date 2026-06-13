# Visible Autonomous Entry - Architecture Review and Revised Plan

**Reviewed:** 2026-06-13  
**Repository:** `jinx120/crypto-swing-bot` at `a6b6bee60ffb6abb9957ffe96387263335e1a400`  
**Source draft:** `2026-06-13-visible-autonomous-entry-design.md`  
**Disposition:** Approve the goal, revise the implementation order and several contracts before coding.

---

## 1. Executive decision

The draft identifies the primary visible symptom correctly: `PortfolioSupervisor.start()` is
never called on web-app boot, so a container restart leaves the trading loop idle.

Do **not** implement auto-start as the first change, though. The current code explicitly says
that supervisor state is single-writer and not synchronized, while web request threads already
call `reload()`, `flatten()`, `halt()`, `pause()`, and other mutating methods. Auto-start would
make those races routine. The broker adapter also converts every `get_position()` exception into
"no position," which is unsafe for an autonomous loop.

The safe order is:

1. Harden lifecycle, synchronization, broker truth, and shutdown.
2. Persist desired lifecycle state and auto-resume paper mode.
3. Add durable cycle/decision telemetry and durable trade history.
4. Add a deliberately scoped proof-of-life mechanism.
5. Simplify the dashboard around the new truthful API.

The original draft is a useful **design document**, but it is not yet an executable
implementation plan: it lacks exact schema contracts, migration behavior, failure semantics,
and task-level test steps.

---

## 2. Findings requiring changes

### Critical 1: Auto-start exposes known thread-safety violations

`PortfolioSupervisor` documents a single-writer invariant, but the web layer mutates it from
request threads. `reload()` can rebuild `_strategies`, `_store`, and `_portfolio_risk` while the
loop is inside `tick_all()`. `status()` can read those structures concurrently. Auto-start makes
this the normal operating mode.

**Required correction:** add one supervisor-owned synchronization mechanism before auto-start.
For this codebase, a re-entrant lock around lifecycle, mutation, tick, and status methods is the
smallest acceptable change. A command queue owned by the loop is cleaner long-term, but larger.

### Critical 2: Broker errors are treated as "no position"

`AlpacaBroker.get_position()` catches every exception and returns `None`. Authentication,
timeout, rate-limit, and network failures therefore look identical to a confirmed flat account.
This can clear persisted state during reconciliation or allow a duplicate buy.

**Required correction:** return `None` only for Alpaca's confirmed position-not-found response.
Propagate all other errors and record them as reconcile/decision failures.

### Critical 3: A live EMA crossover cannot guarantee a prompt paper entry

An EMA 9/21 cross is true only on the bar where the cross occurs. Finding a cross somewhere in
five days of history does not mean the latest bar is crossing. After restart, the bot may wait
hours or days. Therefore these two requirements cannot both be promised:

- use a genuine crossover strategy; and
- guarantee a paper position opens within a bounded number of live cycles.

**Required correction:** choose one explicit acceptance contract:

- **Recommended:** add a paper-only, opt-in proof-of-life profile/signal that fires once on fresh
  data and still passes through the real `_maybe_enter` risk, sizing, broker, and persistence
  path. It must be impossible in live mode and visibly labeled as a probe.
- Or keep `ma_cross` as the real strategy and remove the bounded-entry promise.

Do not silently lower thresholds and call the result guaranteed.

### Critical 4: Submitted order is recorded as a filled position

`_maybe_enter()` submits a market buy, then immediately persists an `OpenPosition` using the
last candle close. It does not confirm fill status, filled quantity, or fill price. A visible
position can therefore be fictional even when Alpaca rejected, delayed, or partially filled the
order.

**Required correction:** model `pending_order -> broker-confirmed open position`, or perform a
bounded post-submit reconciliation and persist only broker-confirmed fill data. Telemetry must
distinguish `ORDER_SUBMITTED`, `ORDER_PENDING`, `ENTERED`, and `ORDER_FAILED`.

### High 1: The proposed telemetry stages do not match code ownership

Ingest/warm and account fetch happen in `PortfolioSupervisor.tick_all()`. Reconcile currently
happens only in `start()`. Manage/decide happen in `Orchestrator.tick()` and are mutually
exclusive. Persistence is scattered across orchestrator and supervisor.

**Required correction:** cycle telemetry is coordinated by `PortfolioSupervisor`, with structured
results returned by orchestrator operations. Do not wrap an imagined five-stage pipeline only
inside `Orchestrator.tick()`.

### High 2: `halt` must not clear desired-running state

`halt()` activates a persistent entry kill switch; it does not stop the loop. Keeping the loop
running is important because open positions still need management. Setting `running_desired`
false on halt would leave positions unmanaged after restart.

**Required correction:** only explicit `stop` sets `running_desired=false`. `halt` keeps the loop
desired/running but blocks new entries. Show these states separately.

### High 3: Lifecycle shutdown and duplicate-loop behavior need hardening

The poller starts before Uvicorn and is never stopped. The supervisor is not stopped by app
shutdown. `stop()` clears `_thread` even if its two-second join times out, allowing a later start
to create another loop.

**Required correction:** own poller and supervisor startup/shutdown in one FastAPI lifespan,
retain a live thread reference after join timeout, and reject/recover from duplicate starts.

### High 4: Existing profiles cannot be silently deleted or overwritten

The five "noise" strategies are runtime database state, not repository seed data. Deleting them
on boot is destructive. Seeding profiles "if absent" also does not make them fixed, because an
existing profile with the same name can drift.

**Required correction:** preserve existing profiles. Add versioned managed profiles with explicit
ownership metadata. A clean-canvas migration must back up existing armed/profile state and be an
explicit one-time operation or an opt-in deployment mode.

### High 5: Hiding strategy creation in the frontend does not create a fixed canvas

Profiles can still be created/armed through profile APIs, discovery, and decision-brain actions.

**Required correction:** define whether "fixed strategies" is merely a simplified UI or an
enforced server mode. If enforced, profile/discovery/brain mutation endpoints must reject changes
while managed-canvas mode is active.

### High 6: Trade history and chart markers are not durable

`TradeJournal` is in memory. Restarting loses closed trades, metrics, and chart markers. This
conflicts with a dashboard intended to visibly prove autonomous behavior.

**Required correction:** persist orders/fills/trades in SQLite and build journal/metrics/markers
from durable records.

### Medium 1: Reliability score semantics are underspecified

Manage and decide are mutually exclusive. Missing credentials, disabled loop, and skipped stages
must not be scored as ordinary stage failures without a defined denominator. An average of stage
ratios can also hide a completely broken critical stage.

**Required correction:** use `ok | failed | skipped` outcomes. Exclude `skipped` from per-stage
denominators. Define overall cycle success as all required stages for that cycle succeeding.
Display the worst critical-stage score alongside the overall cycle-completion ratio.

### Medium 2: Freshness must use closed-bar semantics and tolerance

The engine contract says the last candle is closed. The current data path does not explicitly
remove an in-progress bar, and "`older than one timeframe`" is too strict around provider delay.

**Required correction:** normalize to closed bars, record latest closed-bar timestamp, and use a
documented tolerance such as `expected_close + provider_grace`. Test boundary times.

### Medium 3: `/api/health` needs separation from process health and the existing Health UI

The current Health tab reports usage-agent runs. Trading-loop reliability is a different concept.

**Required correction:** expose separate contracts:

- `/api/health/live`: process is serving.
- `/api/health/ready`: required dependencies/configuration are usable.
- `/api/health/trading`: desired/running state, last cycle, stage ratios, and decisions.

The UI may combine them, but the API must not.

---

## 3. Revised behavioral contract

### 3.1 Lifecycle states

Persist these separately:

| Field | Meaning |
|---|---|
| `mode` | `paper` or `live`; restart defaults to paper unless a later design safely persists live |
| `running_desired` | operator wants the loop active across restart |
| `running_actual` | loop thread is alive |
| `paused` | loop runs and manages positions, but no new entries |
| `halted` | persistent kill switch blocks new entries; loop still manages positions |
| `startup_error` | most recent auto-start failure, visible in API/UI |

Auto-start rule:

```text
On application lifespan startup:
  start poller
  if mode == paper
     and running_desired
     and at least one managed/armed strategy exists:
       attempt supervisor.start()
       record startup_error instead of crashing the web app on failure
```

`POST /api/control/start` sets desire true only after a successful start.  
`POST /api/control/stop` sets desire false, then stops.  
`halt`, `pause`, and `resume` do not alter desire.  
App shutdown stops threads without changing desire.

For a fresh managed-canvas installation, an explicit deployment setting may initialize
`running_desired=true`. Existing installations must not be silently opted in.

### 3.2 Cycle and decision outcomes

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

Stable decision codes:

```text
PAUSED
HALTED
BROKER_POSITION_EXISTS
RISK_BLOCKED
REGIME_BLOCKED
SIGNAL_BELOW_THRESHOLD
ATR_INVALID
SIZE_ZERO
PORTFOLIO_BLOCKED
ORDER_SUBMITTED
ORDER_PENDING
ENTERED
ORDER_FAILED
MANAGED_NO_EXIT
EXIT_SUBMITTED
EXITED
ERROR
```

Store codes separately from human-readable reasons. Reasons may change; codes are API/test
contracts. Sanitize and length-limit exception messages before persistence.

Manage is required only when a position exists. Decide is required only when flat. A skipped
stage is not a failure.

### 3.3 Reliability

Over the latest 200 completed cycles:

- Per-stage reliability = `ok / (ok + failed)`, excluding skipped.
- Cycle-completion reliability = cycles where every required stage succeeded / completed cycles.
- Critical-stage floor = minimum reliability among ingest, reconcile, and persist.
- Show sample counts and window timestamps; never show a bare percentage.
- A stopped-by-desire loop is `inactive`, not healthy or unhealthy.
- A desired-but-not-running loop is immediately unhealthy, independent of the rolling score.

### 3.4 Proof-of-life

Recommended design:

- Keep `btc_trend` and `eth_trend` as honest EMA-based trend strategies.
- Add a separate `paper_probe` managed profile only when
  `SWINGBOT_ENABLE_PAPER_PROBE=1`.
- The probe fires once on fresh closed-bar data, then records a durable completion marker.
- It goes through regime/risk/sizing/portfolio/order/fill/persistence code.
- It is rejected when `mode != paper`.
- The dashboard labels it `proof-of-life probe`, not a trading strategy.

If a third probe profile is unacceptable, remove the bounded live-entry acceptance criterion.
There is no honest deterministic alternative using market-dependent crossover signals.

---

## 4. Revised component boundaries

| Responsibility | Files |
|---|---|
| Lifecycle persistence | `src/swingbot/profiles.py` or new `src/swingbot/runtime_state.py` |
| Lifespan/thread ownership | `src/swingbot/webmain.py`, `src/swingbot/web.py`, `src/swingbot/supervisor.py`, `src/swingbot/data/poller.py` |
| Broker truth/order state | `src/swingbot/broker/alpaca.py`, `src/swingbot/broker/base.py`, `src/swingbot/orchestrator.py`, `src/swingbot/types.py` |
| Cycle/decision telemetry | new `src/swingbot/telemetry.py`, `src/swingbot/supervisor.py`, `src/swingbot/orchestrator.py` |
| Durable trades | `src/swingbot/state.py` or new `src/swingbot/trade_store.py`, `src/swingbot/supervisor.py` |
| Managed profiles | new `src/swingbot/managed_profiles.py`, `src/swingbot/confluence.py`, new signal modules |
| Health API | `src/swingbot/web.py` |
| Clean dashboard | `frontend/src/pages/Dashboard.jsx`, `frontend/src/pages/Health.jsx`, `frontend/src/components/*`, `frontend/src/api.js` |

Prefer dedicated stores/modules over expanding `profiles.py` and `state.py` into unrelated
responsibilities.

---

## 5. Revised implementation sequence

### Phase 0: Capture the current failure with acceptance tests

Add tests that demonstrate:

- web app startup currently leaves a desired paper loop idle;
- a non-404 broker position error is propagated;
- trade history disappears after supervisor rebuild;
- concurrent `tick_all()` and `reload()` are serialized after the fix;
- a timed-out stop cannot create a second loop.

Do not change strategy behavior yet.

### Phase 1: Make autonomous operation safe

1. Add supervisor synchronization and lifecycle-state inspection.
2. Distinguish broker position-not-found from broker failure.
3. Harden start/stop/idempotency and thread references.
4. Move poller/supervisor cleanup into FastAPI lifespan.
5. Add tests for start, stop, shutdown, restart desire, missing credentials, and duplicate starts.

Exit criterion: enabling auto-start cannot create two loop threads, erase a position on broker
error, or race a request-thread mutation.

### Phase 2: Persist desire and auto-resume paper mode

1. Add a dedicated runtime-state record/schema migration.
2. Update start/stop semantics exactly as defined in section 3.1.
3. Add lifespan auto-start with visible `startup_error`.
4. Keep web API available when auto-start fails.

Exit criterion: restart resumes a previously desired paper loop; explicit stop survives restart;
halted/paused loops still resume to manage positions.

### Phase 3: Make outcomes durable and truthful

1. Add structured cycle/decision records with a rolling retention policy.
2. Refactor orchestrator entry gates to return a structured `DecisionResult`.
3. Add order/pending/fill state and broker-confirmed position persistence.
4. Persist trades and build journal/metrics from SQLite.
5. Add `/api/health/live`, `/api/health/ready`, and `/api/health/trading`.

Exit criterion: every cycle has a terminal record; every no-entry has a stable reason code;
restart preserves trades, markers, and the last decision.

### Phase 4: Add managed strategies and optional proof-of-life

1. Add EMA with tests.
2. Add honest trend strategy signal/profile definitions.
3. Add versioned managed-profile reconciliation without deleting user profiles.
4. Add opt-in paper probe, or formally remove bounded-entry acceptance.
5. Disable conflicting profile mutation paths only if managed-canvas mode is intended to be
   enforced server-side.

Exit criterion: managed profile definitions are reproducible, existing data is backed up or
preserved, and proof behavior is clearly separated from strategy behavior.

### Phase 5: Rebuild the dashboard around truthful state

Show:

- desired vs actual running state and startup error;
- broker-confirmed positions and pending orders;
- last cycle/bar timestamp and last decision code/reason;
- realized and unrealized P&L with source timestamps;
- durable entry/exit markers;
- trading reliability with counts and window;
- usage-agent health as a separate section.

Do not remove operational controls needed to recover from failures. Hide or disable strategy
creation only according to the managed-canvas server contract.

### Phase 6: Live acceptance

Run acceptance in paper mode:

1. Back up the data directory.
2. Start from an explicit managed-canvas/probe configuration.
3. Rebuild and restart the container without pressing Start.
4. Verify desired/actual running, fresh closed bars, cycle records, and decision reasons.
5. If the probe is enabled, verify an Alpaca-confirmed fill, durable position, chart marker, and
   persisted completion marker.
6. Restart again and verify no duplicate probe/order and continued position management.
7. Simulate credential/network failure and verify the UI remains available with a failed
   reconcile/ready state, without clearing positions or placing duplicate orders.

---

## 6. Required test matrix

| Area | Required cases |
|---|---|
| Lifecycle | desired start, explicit stop, halt, pause, shutdown, restart, start failure, duplicate start |
| Concurrency | tick vs reload/status/control; SQLite access under loop + requests |
| Broker truth | confirmed flat, confirmed position, not-found, auth error, timeout, rate limit |
| Orders | rejected, pending, partial fill, filled, restart while pending, duplicate prevention |
| Telemetry | every decision code, stage exception, skipped denominator, rolling retention |
| Freshness | empty, stale, provider grace boundary, in-progress bar excluded, fresh closed bar |
| Persistence | last decision, runtime desire, position, pending order, trades, metrics across restart |
| Managed canvas | fresh seed, existing user profiles preserved, version upgrade, mutation enforcement |
| UI | desired-not-running, startup error, flat/no-signal, pending order, open position, stale data |

Regression commands remain:

```bash
pytest -q
cd frontend && npm run build
```

Add a focused integration suite that runs without Alpaca by using a deterministic fake broker and
fake clock. Keep real Alpaca paper acceptance opt-in and clearly labeled.

---

## 7. Revised success criteria

The sub-project is complete only when all are true:

1. A previously desired paper loop resumes after container restart with no button press.
2. Explicit stop remains stopped after restart; halt/pause do not abandon open-position
   management.
3. A broker/network error cannot be mistaken for a flat account.
4. No web control can race supervisor mutation or create a duplicate loop.
5. Every desired cycle produces durable stage outcomes and a stable terminal decision code.
6. Orders and positions shown in the UI are broker-confirmed, not inferred from submission.
7. Trades, metrics, markers, and last decisions survive restart.
8. Reliability reports sample counts, skipped semantics, and desired-but-not-running failure.
9. Existing user profiles are preserved unless an explicit backed-up migration is requested.
10. A bounded paper entry is promised only when the explicit paper probe is enabled; otherwise
    acceptance requires truthful autonomous evaluation, not a guaranteed market-dependent trade.

