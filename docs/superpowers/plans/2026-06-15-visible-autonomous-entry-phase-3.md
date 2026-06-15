# Visible Autonomous Entry Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every strategy cycle, decision, order transition, position, and closed trade durable and truthful, then expose separate live, ready, and trading-health APIs over those facts.

**Architecture:** `PortfolioSupervisor` remains the cycle coordinator because it owns ingest, account access, strategy ordering, and final portfolio persistence. `Orchestrator` returns stable typed `DecisionResult` values for reconcile/manage/decide work, while dedicated lock-protected SQLite stores persist cycle telemetry and trades. `StateStore` gains durable pending orders; broker-confirmed order and position snapshots promote pending orders to positions or closed trades. Health endpoints read lifecycle truth plus the latest 200 completed cycle records without making broker mutations.

**Tech Stack:** Python 3.11+, dataclasses/enums, `sqlite3` with `threading.RLock`, FastAPI, pandas, alpaca-py, pytest.

**Spec basis:** `docs/superpowers/specs/2026-06-13-visible-autonomous-entry-design-reviewed.md` §3.2, §3.3, §4, §5 Phase 3, §6, and success criteria 5-8. `docs/PHASE3_CODEX_HANDOFF.md` is the execution brief; the authoritative spec wins on conflict.

**Reference checkout:** Clean `jinx120/crypto-swing-bot` `master` at `be538df` cloned to `/home/ahmad/crypto-swing-bot` on 2026-06-15.

**Scope:** Backend telemetry, order/fill truth, durable trades, freshness, and health APIs only. Do not change the frontend, add managed profiles or the paper probe, alter lifecycle semantics, or rebuild already-shipped Phase 0/1/2/2.1 behavior.

---

## Locked Contracts

### Decision codes

`DecisionCode` is a string enum and an API/test contract:

```python
class DecisionCode(str, Enum):
    PAUSED = "PAUSED"
    HALTED = "HALTED"
    BROKER_POSITION_EXISTS = "BROKER_POSITION_EXISTS"
    RISK_BLOCKED = "RISK_BLOCKED"
    REGIME_BLOCKED = "REGIME_BLOCKED"
    SIGNAL_BELOW_THRESHOLD = "SIGNAL_BELOW_THRESHOLD"
    ATR_INVALID = "ATR_INVALID"
    SIZE_ZERO = "SIZE_ZERO"
    PORTFOLIO_BLOCKED = "PORTFOLIO_BLOCKED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_PENDING = "ORDER_PENDING"
    ENTERED = "ENTERED"
    ORDER_FAILED = "ORDER_FAILED"
    MANAGED_NO_EXIT = "MANAGED_NO_EXIT"
    EXIT_SUBMITTED = "EXIT_SUBMITTED"
    EXITED = "EXITED"
    ERROR = "ERROR"
```

Reasons are human-readable and may change. Details are JSON-compatible structured data. Persisted exception text must pass through `sanitize_text()` and is capped at 500 characters.

### Cycle ownership and stage semantics

- `PortfolioSupervisor.tick_all()` creates and completes one `CycleRecord` per armed strategy per attempted supervisor cycle.
- Shared warm/ingest outcomes are copied into each affected strategy record.
- `PortfolioSupervisor` calls `Orchestrator.reconcile()` before `Orchestrator.tick()`.
- `Orchestrator.tick()` returns a `DecisionResult`; it does not write telemetry.
- The supervisor determines whether `manage` or `decide` is required from broker-confirmed state after reconciliation. Exactly one is required; the other is `skipped`.
- `persist` describes durable trading-state writes for the strategy cycle. The telemetry append happens last and must still store a terminal record with `persist=failed` when a trading-state write fails.
- A telemetry-store write failure is a supervisor-level infrastructure error and must be logged/raised; it cannot truthfully be represented as a durable record that was never written.

### Order truth

- Before broker submission, generate a unique `client_order_id` and durably write a `PendingOrder` intent. After submission, update it with the broker order ID. This closes the submit-then-crash duplicate window.
- Pending orders block duplicate submissions across cycles and restarts.
- A restart can reconcile an intent by `client_order_id` even when a transport failure/crash prevented storing the broker order ID.
- Partial fills remain pending.
- A buy is promoted to `OpenPosition` only after the broker reports the order filled and `get_position()` confirms the position; persisted quantity and entry price come from broker truth.
- A sell clears `OpenPosition` and records a trade only after the broker reports the order filled and `get_position()` confirms flat.
- A confirmed order-not-found lookup, or a rejected/canceled/expired order snapshot, clears pending state and returns `ORDER_FAILED`. Other lookup errors propagate and retain pending state.
- The first durable submission result is `ORDER_SUBMITTED` for buys and `EXIT_SUBMITTED` for sells. Later unresolved buy cycles return `ORDER_PENDING`; unresolved sell cycles continue to return `EXIT_SUBMITTED`.

### Freshness

Bar timestamps are bar-open timestamps. A bar is closed when:

```text
bar_open + timeframe <= now
```

The latest closed bar is fresh when:

```text
now <= latest_closed_bar_open + timeframe + provider_grace
```

Use a documented default `provider_grace=120` seconds. Never pass an in-progress bar to strategy evaluation, and record the latest closed bar-open timestamp as `bar_ts`.

### Health response semantics

- `/api/health/live`: always `200` with `status="live"` and an ISO-8601 `served_at` timestamp when the process serves the request.
- `/api/health/ready`: `200` with `ready: bool`; no active network call. Missing credentials, no armed strategies, unreadable lifecycle desire, no completed cycle while desired, or a latest critical-stage failure make readiness false and appear in `checks`.
- `/api/health/trading`: `200`; `status` is `inactive` when `running_desired is False`, `unhealthy` when desire is unreadable or desired-but-not-running, and `active` when the desired loop is actually running. The API reports rolling reliability separately and does not invent an unspecified pass threshold.
- Reliability always includes counts and window timestamps. Skipped stages never enter denominators.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/swingbot/types.py` | Shared typed contracts | Add `DecisionCode`, `DecisionResult`, `OrderSide`, `OrderStatus`, `BrokerOrder`, and `PendingOrder`; carry optional confirmed entry order ID on `OpenPosition` |
| `src/swingbot/telemetry.py` | Durable cycle records, sanitization, reliability math | **New** lock-protected SQLite store and pure reliability helpers |
| `src/swingbot/data/market.py` | Closed-bar normalization/freshness | Add pure closed-bar and freshness helpers |
| `src/swingbot/state.py` | Durable positions, risk, pending orders | Add pending-order table/API and matching `StrategyStateView` methods |
| `src/swingbot/broker/alpaca.py` | Broker-confirmed order snapshots | Add `get_order()` serialization and normalized statuses |
| `src/swingbot/broker/base.py` | Broker protocol | Describe order submit/query/position contract used by live orchestrator |
| `src/swingbot/trade_store.py` | Durable closed trades | **New** lock-protected SQLite trade store |
| `src/swingbot/journal.py` | Journal facade | Support optional durable backend while retaining in-memory use for backtests |
| `src/swingbot/orchestrator.py` | Reconcile/manage/decide behavior | Return stable decisions; persist/promote pending orders; record broker-confirmed exits |
| `src/swingbot/supervisor.py` | Cycle coordinator and health source | Build stores, normalize bars, assemble terminal cycle records, expose readiness/trading health |
| `src/swingbot/web.py` | Health HTTP API | Add three separate `/api/health/*` routes |
| `src/swingbot/webmain.py` | Composition root | Wire shared Phase 3 stores/configuration if constructor injection is used |
| `tests/test_types_decisions.py` | Decision contract | **New** enum/result tests |
| `tests/test_telemetry.py` | Telemetry persistence/reliability | **New** retention, restart, stage, sanitization tests |
| `tests/test_market_freshness.py` | Closed-bar/freshness | **New** empty/stale/grace/in-progress boundary tests |
| `tests/test_state_orders.py` | Pending-order persistence | **New** keyed order/restart tests |
| `tests/test_trade_store.py` | Durable trade persistence | **New** strategy filtering, idempotency, restart tests |
| `tests/test_orchestrator_decisions.py` | Stable gate decisions | **New** every entry/manage decision code |
| `tests/test_orchestrator_orders.py` | Order/fill transitions | **New** rejected/pending/partial/filled/restart/duplicate tests |
| `tests/test_supervisor_telemetry.py` | Cycle coordination | **New** stage exception, terminal record, required/skipped tests |
| `tests/test_web_health.py` | Health API contracts | **New** live/ready/trading lifecycle and reliability tests |
| `tests/test_phase3_integration.py` | Deterministic end-to-end restart behavior | **New** fake broker/clock integration suite |
| `docs/ROADMAP_STATUS.md` | Cross-session status | Mark plan ready; after execution record Phase 3 completion and next action |

---

## Execution Rules

For every task: write the focused failing test, run it and confirm the expected failure, implement the smallest production change, run focused tests, run relevant regressions, then commit test and implementation together. Never commit a deliberately red test.

Fresh-clone preflight:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

Expected baseline before Phase 3: `431 passed, 6 skipped`. The clean clone currently has no `.venv`.

---

### Task 1: Add Stable Decision and Order Contracts

**Files:**
- Modify: `src/swingbot/types.py`
- Create: `tests/test_types_decisions.py`

- [x] **Step 1: Write failing contract tests**

```python
from datetime import datetime, timezone

from swingbot.types import (
    BrokerOrder, DecisionCode, DecisionResult, OrderSide, OrderStatus, PendingOrder, Regime,
)


def test_decision_codes_match_phase3_api_contract():
    assert {code.value for code in DecisionCode} == {
        "PAUSED", "HALTED", "BROKER_POSITION_EXISTS", "RISK_BLOCKED",
        "REGIME_BLOCKED", "SIGNAL_BELOW_THRESHOLD", "ATR_INVALID", "SIZE_ZERO",
        "PORTFOLIO_BLOCKED", "ORDER_SUBMITTED", "ORDER_PENDING", "ENTERED",
        "ORDER_FAILED", "MANAGED_NO_EXIT", "EXIT_SUBMITTED", "EXITED", "ERROR",
    }


def test_decision_result_defaults_to_empty_details():
    result = DecisionResult(DecisionCode.PAUSED, "operator paused entries")
    assert result.details == {}


def test_pending_order_carries_restart_safe_entry_context():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pending = PendingOrder(
        client_order_id="swingbot-btc-001", broker_order_id=None,
        symbol="BTC/USD", side=OrderSide.BUY,
        submitted_at=now, requested_qty=0.1, stop=90.0, tp=120.0,
        max_hold_until=now, score_at_entry=0.7, regime_at_entry=Regime.UPTREND,
    )
    assert pending.side is OrderSide.BUY


def test_broker_order_exposes_normalized_fill_truth():
    order = BrokerOrder(
        order_id="buy-1", symbol="BTC/USD", side=OrderSide.BUY,
        status=OrderStatus.PARTIALLY_FILLED, requested_qty=1.0,
        filled_qty=0.4, filled_avg_price=101.0,
    )
    assert order.status is OrderStatus.PARTIALLY_FILLED
```

- [x] **Step 2: Run the tests and verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_types_decisions.py`
Expected: FAIL because the Phase 3 types do not exist.

- [x] **Step 3: Add the contracts**

Add frozen dataclasses and string enums to `types.py`. `DecisionResult.details` uses `field(default_factory=dict)`. `PendingOrder` has `client_order_id`, nullable `broker_order_id`, enough entry context to create an `OpenPosition` after restart, and optional exit context (`exit_reason`, `observed_exit_price`) for a pending sell. `BrokerOrder` carries both client and broker IDs and a nullable `filled_avg_price`. Extend `OpenPosition` with nullable `entry_order_id`; existing serialized positions load it as `None`.

- [x] **Step 4: Run focused and existing type/state tests**

Run: `.venv/bin/python -m pytest -q tests/test_types_decisions.py tests/test_state.py tests/test_state_multi.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/swingbot/types.py tests/test_types_decisions.py
git commit -m "feat: add phase 3 decision and order contracts"
```

---

### Task 2: Add Durable Cycle Telemetry, Reliability, and Closed-Bar Freshness

**Files:**
- Create: `src/swingbot/telemetry.py`
- Modify: `src/swingbot/data/market.py`
- Create: `tests/test_telemetry.py`
- Create: `tests/test_market_freshness.py`

- [x] **Step 1: Write failing telemetry-store tests**

Add tests with these exact outcomes:

- `test_cycle_roundtrip_preserves_stage_outcomes_and_decision`: write one record and compare every loaded field.
- `test_cycle_store_survives_reopen`: close/recreate the store and load the same `cycle_id`.
- `test_retention_keeps_latest_200_per_strategy`: write 205 `btc` and 205 `eth` cycles; each strategy query returns IDs 5-204.
- `test_reliability_excludes_skipped_and_reports_counts_and_window`: one `manage=ok/decide=skipped` and one `manage=skipped/decide=failed` produce one sample for each stage.
- `test_cycle_completion_uses_only_required_manage_or_decide_stage`: the first cycle succeeds and the second fails, producing `successful_cycles=1`, `completed_cycles=2`, and ratio `0.5`.
- `test_critical_floor_is_minimum_of_ingest_reconcile_persist`: construct stage ratios `1.0`, `0.5`, and `0.75`; assert floor `0.5`.
- `test_sanitize_text_removes_control_chars_and_caps_at_500`: assert no newline/NUL remains and result length is 500.

Use this public surface:

```python
store = TelemetryStore(str(tmp_path / "state.db"), retention=200)
store.record(CycleRecord(
    cycle_id="c1", strategy="btc", started_at=start, completed_at=end, bar_ts=start,
    ingest="ok", reconcile="ok", manage="skipped", decide="ok", persist="ok",
    decision_code=DecisionCode.SIGNAL_BELOW_THRESHOLD,
    decision_reason="score below threshold", decision_details={"score": 0.2},
))
rows = store.recent(limit=200, strategy="btc")
report = store.reliability(limit=200)
```

Assert each stage report has `ok`, `failed`, `skipped`, `samples`, and `ratio`; assert the top-level report has `completed_cycles`, `successful_cycles`, `cycle_completion_ratio`, `critical_stage_floor`, `window_started_at`, and `window_completed_at`.

- [x] **Step 2: Write failing freshness boundary tests**

Add tests with these exact outcomes:

- Empty input returns `closed=[]`, `bar_ts=None`, and `fresh=False`.
- At `now=12:14:59`, a `12:00` 15-minute bar is excluded.
- At `now=12:17:00`, a `12:00` 15-minute bar is fresh with 120-second grace.
- At `now=12:17:01`, the same bar is stale.
- With a closed `12:00` bar and in-progress `12:15` bar at `12:16`, `bar_ts` is `12:00`.

Use:

```python
closed = closed_bars(bars, timeframe="15m", now=now)
fresh = closed_bar_freshness(bars, timeframe="15m", now=now, provider_grace=120)
```

- [x] **Step 3: Run the new tests and verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_telemetry.py tests/test_market_freshness.py`
Expected: FAIL because the modules/helpers do not exist.

- [x] **Step 4: Implement telemetry and freshness**

`telemetry.py` defines:

```python
StageOutcome = Literal["ok", "failed", "skipped"]

@dataclass(frozen=True)
class CycleRecord:
    cycle_id: str
    strategy: str
    started_at: datetime
    completed_at: datetime
    bar_ts: datetime | None
    ingest: StageOutcome
    reconcile: StageOutcome
    manage: StageOutcome
    decide: StageOutcome
    persist: StageOutcome
    decision_code: DecisionCode
    decision_reason: str
    decision_details: dict
```

`TelemetryStore` uses one `check_same_thread=False` SQLite connection guarded by an `RLock`, JSON-encodes details, orders completed cycles by `(completed_at DESC, cycle_id DESC)`, and prunes rows older than the latest `retention` rows for the just-written strategy. This preserves at least 200 recent records for every strategy while allowing aggregate latest-200 queries.

`closed_bars()` and `closed_bar_freshness()` are pure helpers in `data/market.py`; they do not use wall-clock time unless the caller explicitly supplies it.

- [x] **Step 5: Run focused and market regressions**

Run: `.venv/bin/python -m pytest -q tests/test_telemetry.py tests/test_market_freshness.py tests/test_market.py tests/test_market_multi.py`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/swingbot/telemetry.py src/swingbot/data/market.py \
  tests/test_telemetry.py tests/test_market_freshness.py
git commit -m "feat: persist cycle telemetry and closed-bar freshness"
```

---

### Task 3: Persist Pending Orders and Query Broker Order Truth

**Files:**
- Modify: `src/swingbot/state.py`
- Modify: `src/swingbot/broker/base.py`
- Modify: `src/swingbot/broker/alpaca.py`
- Create: `tests/test_state_orders.py`
- Modify: `tests/test_alpaca_broker.py`

- [x] **Step 1: Write failing pending-order persistence tests**

Add tests with these exact outcomes:

- Two pending orders written under `btc` and `eth` load independently and appear in `load_all_pending_orders()`.
- A pending order written by one `StateStore` instance loads after reopening the database, retaining client and nullable broker IDs.
- `StrategyStateView(store, "btc")` reads/writes/clears only the `btc` pending order.
- Clearing a pending order leaves the same strategy's `OpenPosition` unchanged.
- Concurrent pending-order and position reads/writes through one `StateStore` connection are serialized without SQLite errors.

Pin this API:

```python
store.save_pending_order(order, strategy="btc")
store.load_pending_order("btc")
store.load_all_pending_orders()
store.clear_pending_order("btc")

view.save_pending_order(order)
view.load_pending_order()
view.clear_pending_order()
```

- [x] **Step 2: Write failing Alpaca order serialization tests**

Fake Alpaca order objects for `new`, `accepted`, `partially_filled`, `filled`, `rejected`, `canceled`, and `expired`. Assert lookup by broker ID and lookup by client order ID return a normalized `BrokerOrder`, including both IDs, `filled_qty`, and nullable `filled_avg_price`. Assert confirmed 404 returns `None`; authentication, timeout, rate-limit, and other errors propagate. Existing `get_position()` error-propagation tests stay green.

- [x] **Step 3: Run tests and verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_state_orders.py tests/test_alpaca_broker.py`
Expected: FAIL because pending-order APIs and `get_order()` do not exist.

- [x] **Step 4: Add the durable table and broker method**

Add an `RLock` around `StateStore`'s shared `check_same_thread=False` connection and cover every existing/new database method. Add a `pending_orders(strategy TEXT PRIMARY KEY, data TEXT NOT NULL)` table. Serialize enums by `.value` and datetimes by `.isoformat()`. Extend `StrategyStateView`; update position serialization to round-trip nullable `entry_order_id`.

Add protocol signatures for `submit_market_buy(symbol, qty, client_order_id) -> BrokerOrder`,
`submit_market_sell(symbol, qty, client_order_id) -> BrokerOrder`,
`get_order(order_id=None, client_order_id=None) -> BrokerOrder | None`, and `get_position(symbol) -> dict | None`.

Alpaca submission requests include `client_order_id` and return the normalized submitted order snapshot. `AlpacaBroker.get_order()` calls `get_order_by_id()` or `get_order_by_client_id()`, returns `None` only for a confirmed 404, propagates every other error, and maps known Alpaca statuses to the normalized enum. Unknown statuses raise `ValueError` instead of being silently treated as pending or filled.

- [x] **Step 5: Run focused state/broker regressions**

Run: `.venv/bin/python -m pytest -q tests/test_state.py tests/test_state_multi.py tests/test_state_threading.py tests/test_state_orders.py tests/test_alpaca_broker.py`
Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/swingbot/state.py src/swingbot/broker/base.py src/swingbot/broker/alpaca.py \
  tests/test_state_orders.py tests/test_alpaca_broker.py
git commit -m "feat: persist pending orders and expose broker order truth"
```

---

### Task 4: Persist Closed Trades and Back the Journal with SQLite

**Files:**
- Create: `src/swingbot/trade_store.py`
- Modify: `src/swingbot/journal.py`
- Create: `tests/test_trade_store.py`
- Modify: `tests/test_journal_metrics.py`

- [x] **Step 1: Write failing durable-trade tests**

Add tests with these exact outcomes:

- Records for `btc` and `eth` round-trip and strategy filters return only matching records.
- A record loads after `TradeStore` is closed/recreated.
- Recording the same `exit_order_id` twice leaves one row.
- A durable `TradeJournal` created after the write exposes the prior trade.
- `compute_metrics(reopened_journal.trades)` returns the same counts/P&L metrics before and after restart.

Pin this API:

```python
store = TradeStore(str(tmp_path / "state.db"))
store.record("btc", trade, symbol="BTC/USD", entry_order_id="buy-1", exit_order_id="sell-1")
store.list(strategy="btc")
journal = TradeJournal(store=store, strategy="btc")
```

- [x] **Step 2: Run tests and verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_trade_store.py tests/test_journal_metrics.py`
Expected: FAIL because `TradeStore` and durable journal mode do not exist.

- [x] **Step 3: Implement the store and compatible journal facade**

`TradeStore` uses an `RLock`, `check_same_thread=False`, and a unique `exit_order_id` primary key so a restart cannot duplicate a confirmed exit. Persist strategy, symbol, both order IDs, all existing `Trade` fields, and insert time. `TradeJournal()` with no arguments keeps current in-memory behavior for backtests. `TradeJournal(store=trade_store, strategy="btc")` delegates `record()` and its `trades` property to SQLite.

- [x] **Step 4: Run journal, metrics, risk, and backtest regressions**

Run: `.venv/bin/python -m pytest -q tests/test_trade_store.py tests/test_journal_metrics.py tests/test_risk.py tests/test_backtest_integration.py tests/test_simulated_broker.py`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/swingbot/trade_store.py src/swingbot/journal.py \
  tests/test_trade_store.py tests/test_journal_metrics.py
git commit -m "feat: persist closed trades and journal history"
```

---

### Task 5: Return Stable Orchestrator Decisions and Enforce Broker-Confirmed Fills

**Files:**
- Modify: `src/swingbot/orchestrator.py`
- Create: `tests/test_orchestrator_decisions.py`
- Create: `tests/test_orchestrator_orders.py`
- Modify: `tests/test_orchestrator.py`
- Modify: `tests/test_orchestrator_control.py`
- Modify: `tests/test_orchestrator_portfolio.py`

- [x] **Step 1: Write failing entry/manage decision-code tests**

Create deterministic fixtures that force every orchestrator-owned code:

```text
PAUSED, HALTED, BROKER_POSITION_EXISTS, RISK_BLOCKED, REGIME_BLOCKED,
SIGNAL_BELOW_THRESHOLD, ATR_INVALID, SIZE_ZERO, PORTFOLIO_BLOCKED,
ORDER_SUBMITTED, ORDER_PENDING, ENTERED, ORDER_FAILED,
MANAGED_NO_EXIT, EXIT_SUBMITTED, EXITED, ERROR
```

Assert `_maybe_enter()`, `_manage_open()`, `reconcile()`, `flatten()`, and `tick()` return `DecisionResult` rather than `None`. Reasons must be useful but tests pin codes and selected structured details, not complete prose.

- [x] **Step 2: Write failing order-transition tests**

Use a deterministic fake broker with scripted `get_order()` and `get_position()` results:

Add tests with these exact outcomes:

- Buy intent is persisted with a client order ID before broker submission; successful submission updates the broker order ID, returns `ORDER_SUBMITTED`, and leaves position empty.
- Reopening state with a pending buy submits no duplicate and reconciles by client order ID when broker order ID is absent.
- A submit transport timeout keeps the durable intent because the broker may have accepted it; the next reconcile queries by client order ID.
- A confirmed order-not-found response clears the intent and returns `ORDER_FAILED`; auth/timeout/rate-limit lookup errors retain it and propagate.
- Partial buy fill remains pending and leaves position empty.
- Filled buy remains pending until `get_position()` confirms; then `ENTERED` persists broker quantity/average price and confirmed entry order ID.
- Rejected buy clears pending and returns `ORDER_FAILED`.
- Submitted sell returns `EXIT_SUBMITTED` and keeps the open position.
- Filled sell plus confirmed flat records one actual-fill-price trade and clears position/pending.
- Authentication `APIError`, `TimeoutError`, and rate-limit `APIError` propagate from reconcile unchanged.

- [x] **Step 3: Run new tests and verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_orchestrator_decisions.py tests/test_orchestrator_orders.py`
Expected: FAIL because orchestrator methods return `None` and infer fills.

- [x] **Step 4: Refactor reconcile and pending-order promotion**

`reconcile(now)` first resolves a durable pending order, using broker order ID when present and client order ID otherwise:

```text
confirmed not-found or rejected/canceled/expired -> clear pending, ORDER_FAILED
new/accepted/partial      -> keep pending, ORDER_PENDING or EXIT_SUBMITTED
filled buy + position     -> save broker-confirmed OpenPosition, clear pending, ENTERED
filled buy + no position  -> keep pending, ORDER_PENDING
filled sell + flat        -> record durable trade, clear position/pending, EXITED
filled sell + position    -> keep pending, EXIT_SUBMITTED
```

When there is no pending order, retain existing broker source-of-truth adoption/clear behavior, but return a structured result and never turn broker exceptions into flat state.

- [x] **Step 5: Refactor decide/manage/flatten**

Map each gate to its stable code. On buy/sell, save a client-order intent before calling the broker, then update it with the returned broker order ID. A definitive rejection clears the intent and returns `ORDER_FAILED`; an ambiguous transport failure retains the intent and returns/records `ERROR` so the next reconcile can query by client ID. Do not save `OpenPosition` on buy submission, clear it on sell submission, or write a trade before confirmed fill/flat state. `tick()` checks pending state before deciding/managing and returns the matching pending code.

Set `orch.halted` separately from `orch.paused`; supervisor wiring comes in Task 6.

- [x] **Step 6: Run focused and orchestrator regressions**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_orchestrator.py \
  tests/test_orchestrator_control.py \
  tests/test_orchestrator_portfolio.py \
  tests/test_orchestrator_decisions.py \
  tests/test_orchestrator_orders.py
```

Expected: PASS, with old assertions updated to broker-confirmed transition semantics.

- [x] **Step 7: Commit**

```bash
git add src/swingbot/orchestrator.py tests/test_orchestrator.py \
  tests/test_orchestrator_control.py tests/test_orchestrator_portfolio.py \
  tests/test_orchestrator_decisions.py tests/test_orchestrator_orders.py
git commit -m "feat: return stable decisions and confirm broker fills"
```

---

### Task 6: Coordinate and Persist One Terminal Record per Strategy Cycle

**Files:**
- Modify: `src/swingbot/supervisor.py`
- Modify: `src/swingbot/webmain.py`
- Create: `tests/test_supervisor_telemetry.py`
- Modify: `tests/test_supervisor.py`
- Modify: `tests/test_supervisor_control.py`

- [x] **Step 1: Write failing supervisor telemetry tests**

Add tests with these exact outcomes:

- One `tick_all()` over two strategies writes two completed records with distinct IDs.
- A confirmed-flat cycle records `manage=skipped`, `decide=ok`.
- A confirmed-position cycle records `manage=ok`, `decide=skipped`.
- Warm failure records `ingest=failed`, terminal `ERROR`, and does not submit an order.
- Reconcile exception records `reconcile=failed`, terminal `ERROR`, and preserves stored position.
- Decide exception records `decide=failed`, terminal `ERROR`.
- Manage exception records `manage=failed`, terminal `ERROR`.
- Final risk/portfolio write exception records `persist=failed`.
- An in-progress bar is excluded and `bar_ts` points to the latest closed bar.
- Persisted exception reason contains no control characters and is at most 500 characters.

- [x] **Step 2: Run tests and verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_supervisor_telemetry.py`
Expected: FAIL because the supervisor does not own a telemetry store or terminal cycle assembly.

- [x] **Step 3: Wire shared durable stores during build**

Construct one `TelemetryStore(state_db)` and one `TradeStore(state_db)` per supervisor. Inject `TradeJournal(store=trade_store, strategy=name)` into each orchestrator so reload/build cannot erase history. Keep all mutations under the existing `_state_lock`; do not acquire `_lifecycle_lock` while holding it.

- [x] **Step 4: Refactor warm/ingest and cached provider**

Make `_warm(now)` return per-timeframe ingest results instead of swallowing all errors. `CachedProvider.get_candles()` filters to closed bars using the supplied cycle clock; the supervisor records latest closed `bar_ts` and freshness details. A strategy with no closed/fresh bar receives `ingest=failed`, an `ERROR` decision, and a terminal record without entering.

- [x] **Step 5: Assemble terminal cycle records in `tick_all()`**

For each sorted strategy:

```text
create cycle_id + started_at
copy ingest outcome + bar_ts
attempt reconcile
inspect confirmed position/pending state
run required manage or decide path
attempt final risk/portfolio persistence
record completed CycleRecord in a finally-style terminalization path
```

The strategy-local failure must not abort records for later strategies. Set `orch.paused` and `orch.halted` from supervisor state each cycle. Preserve deterministic strategy priority and existing summary/snapshot behavior.

- [x] **Step 6: Read journal and metrics directly from durable trades**

Replace `_trades()` aggregation over currently built orchestrators with `TradeStore.list(strategy=strategy)`, so `journal()`, `metrics()`, go-live checks, and frontend markers survive supervisor rebuild and process restart.

- [x] **Step 7: Run focused supervisor regressions**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_supervisor.py tests/test_supervisor_control.py \
  tests/test_supervisor_safety.py tests/test_supervisor_telemetry.py
```

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add src/swingbot/supervisor.py src/swingbot/webmain.py \
  tests/test_supervisor.py tests/test_supervisor_control.py tests/test_supervisor_telemetry.py
git commit -m "feat: persist terminal telemetry for every strategy cycle"
```

---

### Task 7: Add Separate Live, Ready, and Trading Health APIs

**Files:**
- Modify: `src/swingbot/supervisor.py`
- Modify: `src/swingbot/web.py`
- Create: `tests/test_web_health.py`

- [x] **Step 1: Write failing health-contract tests**

Add tests with these exact outcomes:

- Live returns `200`, `status=live`, and parseable `served_at`, independent of trading state.
- Ready returns false with named failed checks for missing credentials and no armed strategy.
- Ready returns false when the latest completed cycle has failed ingest/reconcile/persist.
- Trading returns `inactive` when `running_desired=False`.
- Trading returns `unhealthy` immediately when `running_desired=True` and `running_actual=False`, even with perfect rolling reliability.
- Trading returns `unhealthy` when `running_desired=None`.
- Trading returns `active` when desired and actual are true, and includes last cycle/decisions/counts/window.
- Trading stage denominators exclude skipped records.
- Every ratio is adjacent to numerator/denominator counts and window timestamps; no response contains a standalone percentage field.

Use a controller fake exposing `readiness()` and `trading_health()` for route tests, plus real-supervisor tests for lifecycle/reliability composition.

- [x] **Step 2: Run tests and verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_web_health.py`
Expected: FAIL with 404s and missing supervisor health methods.

- [x] **Step 3: Implement supervisor health read models**

`readiness()` and `trading_health()` acquire `_state_lock` only for a consistent snapshot, call `lifecycle_state()` before taking `_state_lock` when lifecycle data is needed, and return JSON-compatible dicts. They read telemetry; they never submit/query an order or make a new broker/network call.

`trading_health()` includes:

```text
status, lifecycle, last_cycle, last_decisions_by_strategy,
reliability { stages, completed_cycles, successful_cycles,
cycle_completion_ratio, critical_stage_floor, window_started_at, window_completed_at }
```

- [x] **Step 4: Add the three routes**

```python
@app.get("/api/health/live")
def health_live():
    return {"status": "live", "served_at": datetime.now(timezone.utc).isoformat()}

@app.get("/api/health/ready")
def health_ready():
    return controller.readiness()

@app.get("/api/health/trading")
def health_trading():
    return controller.trading_health()
```

These are read-only and do not require the control token.

- [x] **Step 5: Run web and lifecycle regressions**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_web_health.py tests/test_web_read.py tests/test_web_control.py \
  tests/test_web_desire.py tests/test_web_lifespan.py \
  tests/test_supervisor_autostart.py tests/test_supervisor_safety.py
```

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add src/swingbot/supervisor.py src/swingbot/web.py tests/test_web_health.py
git commit -m "feat: expose live ready and trading health APIs"
```

---

### Task 8: Add Deterministic Phase 3 Integration Coverage and Close the Plan

**Files:**
- Create: `tests/test_phase3_integration.py`
- Modify: `docs/ROADMAP_STATUS.md`
- Modify: this plan only to check completed steps during execution

- [x] **Step 1: Write deterministic fake broker and fake clock integration tests**

The suite must run without Alpaca and cover:

Add tests with these exact outcomes:

- Restart with a pending buy submits no duplicate; a later scripted fill promotes exactly one position.
- Confirmed exit survives supervisor restart and appears in journal, metrics, and the journal fields consumed as chart markers.
- Scripted auth, timeout, and rate-limit errors each create a failed-reconcile terminal record without clearing position.
- After 205 cycles, health reliability uses exactly the latest 200 completed records.
- Desired-but-not-running returns `unhealthy` even when all retained cycle records succeeded.

The fake broker scripts account, position, order, auth error, timeout, and rate-limit outcomes. The fake clock supplies exact cycle and bar-boundary timestamps.

- [x] **Step 2: Run integration and all Phase 3 focused tests**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_types_decisions.py tests/test_telemetry.py tests/test_market_freshness.py \
  tests/test_state_orders.py tests/test_trade_store.py \
  tests/test_orchestrator_decisions.py tests/test_orchestrator_orders.py \
  tests/test_supervisor_telemetry.py tests/test_web_health.py tests/test_phase3_integration.py
```

Expected: PASS.

- [x] **Step 3: Run the full Python regression gate**

Run: `.venv/bin/python -m pytest -q`
Expected: all tests pass; the baseline 431 passed/6 skipped increases by the new Phase 3 tests.

- [x] **Step 4: Run lint and graph update**

Run:

```bash
.venv/bin/python -m ruff check src tests
python3 -m graphify update .
git status --short
```

Expected: ruff passes; graphify updates only its expected tracked artifacts, if any; no frontend files changed.

- [x] **Step 5: Verify frontend was untouched**

Run: `git diff --name-only -- frontend`
Expected: no output. Do not run or modify the frontend build for this backend-only phase unless an unexpected frontend change appears.

- [x] **Step 6: Update roadmap status**

After all gates pass, update `docs/ROADMAP_STATUS.md` with the exact test counts, shipped Phase 3 contracts, and NEXT ACTION = Phase 4 plan. Do not claim live Alpaca acceptance; that remains Phase 6.

- [x] **Step 7: Commit integration coverage and status**

```bash
git add tests/test_phase3_integration.py docs/ROADMAP_STATUS.md
git commit -m "test: cover phase 3 durable trading outcomes"
```

---

## Self-Review

### Spec coverage

- Structured cycle records, stable decisions, terminal records, and 200-cycle reliability: Tasks 1, 2, 5, 6, 7.
- Manage/decide mutually exclusive required-stage semantics and skipped denominators: Tasks 2, 6, 7.
- Broker-confirmed pending/order/fill truth, partial/rejected/restart/duplicate behavior: Tasks 1, 3, 5, 8.
- Durable trades, metrics, and existing journal-derived chart markers: Tasks 4, 6, 8.
- Separate live/ready/trading contracts and desired-but-not-running override: Task 7 and Task 8.
- Closed-bar freshness with provider grace and boundary tests: Task 2 and Task 6.
- Broker error truth for auth/timeout/rate limit: Task 5 and Task 8.

### Explicit deferrals

- Frontend rendering of the new health/trading facts: Phase 5.
- Managed profiles and optional paper proof-of-life probe: Phase 4.
- Real Alpaca paper acceptance and container restart acceptance: Phase 6.
- Reworking backtest `SimulatedBroker` onto the live broker protocol: not required; its existing backtest-only contract remains unchanged.

### Placeholder scan

Placeholder scan passed. Every named test has a pinned expected outcome.
