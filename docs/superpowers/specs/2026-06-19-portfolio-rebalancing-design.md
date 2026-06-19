# Portfolio Rebalancing Layer — Design Spec

**Date:** 2026-06-19
**Status:** Approved for planning
**Inspired by:** the rebalancing concept in `degencodebeast/rebalancr` (intelligent rebalancing
logic only — no blockchain / DeFi).

---

## 1. Problem

The `PortfolioSupervisor` runs N strategies concurrently. Winning strategies accumulate equity and
grow to consume a disproportionate share of the portfolio. There is no mechanism to:

- declare how capital *should* be split across strategies,
- detect when actual allocation has drifted from that target, or
- redistribute capital back toward target.

Today every strategy sizes off **total account equity** (`RiskManager.size(equity=acct["equity"])`),
so there is no per-strategy budget at all.

## 2. Goal

Add a **portfolio rebalancing layer** that:

1. Lets the user set a **target weight per strategy** (persisted in SQLite).
2. **Detects drift** between actual and target allocation against a configurable threshold.
3. Corrects drift in one of two modes:
   - **Soft** — constrain *future* position sizing only (never sells).
   - **Hard** — actively *trim* overweight positions.
4. Applies **smart timing** so it doesn't churn: skip on high volatility, account for asset
   correlation, skip when fee cost exceeds benefit, and respect a minimum interval.
5. Integrates with the supervisor, position sizing, telemetry, the API, and the dashboard.
6. **Never** violates kill switches / circuit breakers, **never** forces an entry, and honors the
   paper/live gate.

## 3. Design Decisions (locked)

| Decision | Choice | Rationale |
|---|---|---|
| Allocation basis | **% of total equity**: `allocated_equity(S) = target_weight(S) × total_equity` | Directly satisfies "read allocated equity not total"; reuses existing equity/deployed math in `_make_gate`. Weights sum to ≤1.0; remainder is an intentional cash buffer. |
| Hard-mode trim size | **Minimal** — sell only enough to drop just under `target + threshold` | Fewer fees; honors the fee-vs-benefit rule; partial close leaves the orchestrator's stop intact. |
| Smart-timing guards | **Lightweight** — vol skip, correlation cluster guard, fee/benefit, min-interval | Matches the four required guards; a full correlation optimizer is YAGNI and too heavy for CPU. |
| Execution site / default | **Inside `tick_all`, default mode = `soft`, `enabled = false`** | Preserves single-writer invariant; SOFT can never place a surprise sell; HARD/enable are explicit opt-ins. |

## 4. Architecture

A new pure-logic module + thin supervisor wiring, mirroring the existing `risk.py` /
`portfolio_risk.py` style (dataclasses + no-IO manager).

### 4.1 New module: `src/swingbot/rebalance.py` (pure logic, no IO)

```python
@dataclass(frozen=True)
class RebalanceSettings:
    enabled: bool = False
    mode: str = "soft"                 # "soft" | "hard"
    drift_threshold: float = 0.05      # 5% absolute weight drift
    min_interval_minutes: int = 1440   # 1 / day
    vol_skip_threshold: float = 0.05   # recent return-stdev above which we skip a symbol
    vol_lookback: int = 24             # bars used for vol + correlation
    fee_rate: float = 0.0025           # per-side taker fee estimate
    benefit_factor: float = 1.0        # require drift_value ≥ benefit_factor × round-trip fee
    correlation_threshold: float = 0.8 # symbols above this form a "cluster"
    cash_buffer_frac: float = 0.0      # reserved, weights may sum to ≤ 1 - cash_buffer_frac

@dataclass(frozen=True)
class StrategyAllocation:
    name: str
    symbol: str
    target_weight: float
    deployed_value: float
    actual_weight: float               # deployed_value / total_equity
    drift: float                       # actual_weight - target_weight

@dataclass
class RebalanceState:                  # persisted
    last_rebalance_at: str = ""        # ISO8601 UTC, "" = never

@dataclass(frozen=True)
class TrimAction:
    name: str
    symbol: str
    qty: float                         # qty to SELL (>0)
    value: float
    reason: str

@dataclass(frozen=True)
class RebalanceResult:
    ran: bool
    skipped_reason: str                # "" if ran
    allocations: list[StrategyAllocation]
    trims: list[TrimAction]            # empty in soft mode
    mode: str
```

Pure functions / `Rebalancer` methods (all deterministic, no IO, fully unit-testable):

- `compute_allocations(deployed: dict[name,float], symbols: dict[name,str], targets: dict[name,float], total_equity: float) -> list[StrategyAllocation]`
- `allocated_equity(name, targets, total_equity) -> float` — `target_weight × total_equity` (defaults to equal-weight `1/N` for any strategy without an explicit target).
- `detect_drift(allocations, threshold) -> list[StrategyAllocation]` — those with `drift > threshold` (overweight only; underweight is corrected passively by soft sizing).
- `correlation_clusters(returns: dict[symbol, Series], threshold) -> list[set[symbol]]` — group symbols whose pairwise corr ≥ threshold.
- `recent_volatility(returns: Series) -> float` — stdev of recent returns.
- `plan_trims(drifted, prices, total_equity, settings, returns_by_symbol) -> (list[TrimAction], skip_reasons)` applying, per overweight strategy:
  - **vol guard:** skip if `recent_volatility(symbol) > vol_skip_threshold`.
  - **correlation guard:** assess drift at *cluster* level — if an overweight symbol is in a cluster with an underweight one, the offset reduces effective drift, avoiding double-trimming correlated exposure.
  - **fee/benefit guard:** `trim_value = deployed - (target + threshold) × total_equity` (the minimal trim notional). Skip if `trim_value < min_trim_notional`, where `min_trim_notional = benefit_factor × 2 × fee_rate × total_equity` — i.e. don't churn round-trip fees on a rebalance too small to matter at the portfolio level. (`benefit_factor` tunes how many fee-multiples of value a trim must move to be worth it.)
  - emit a `TrimAction` of `qty = trim_value / price` otherwise (minimal trim).
- `Rebalancer.evaluate(now, account, strategies, prices, returns_by_symbol) -> RebalanceResult`:
  - **min-interval guard:** if `now - last_rebalance_at < min_interval_minutes` → `RebalanceResult(ran=False, skipped_reason="min interval")`.
  - compute allocations + drift; in **soft** mode return `ran=True, trims=[]` (sizing is enforced elsewhere); in **hard** mode return planned trims.

### 4.2 Persistence (reuse existing SQLite stores — no new DB files)

- **Target weights** → `ProfileStore.set_meta("rebalance_targets", json)` / `get_meta`, plus
  helpers `get_rebalance_targets() -> dict[name,float]` / `set_rebalance_targets(dict)`.
- **Rebalance settings** → `ProfileStore.get/set_meta("rebalance_settings", json)` with
  `get_rebalance_settings() -> dict` / `set_rebalance_settings(dict)` (merge-on-write, mirroring
  `get/set_portfolio_settings`).
- **Rebalance runtime state** (`last_rebalance_at`) → new `StateStore` table
  `rebalance_state (id INTEGER PRIMARY KEY, data TEXT)`, mirroring `portfolio_risk`, with
  `save_rebalance_state` / `load_rebalance_state`.

Validation on write: each weight in `[0,1]`, `sum(weights) ≤ 1.0`, names must be known strategies.

### 4.3 Supervisor wiring (`supervisor.py`)

1. **`build()`** — construct `RebalanceSettings(**profiles.get_rebalance_settings())`, load targets
   and `RebalanceState`, instantiate `self._rebalancer = Rebalancer(settings, state)`.
2. **Soft sizing — the "allocated equity not total" change.** `Orchestrator.tick()` gains an optional
   `sizing_equity: float | None = None`; when provided, `_maybe_enter` passes it to
   `risk.size(equity=sizing_equity, …)` (everything else — `risk.start_day`, gate, daily loss —
   keeps using real `acct["equity"]`). In `tick_all`, when rebalancing is enabled the supervisor
   computes `sizing_equity = allocated_equity(name, targets, total_equity)` per strategy and passes
   it in. When disabled, `sizing_equity=None` ⇒ **current behavior is byte-for-byte preserved.**
3. **Soft cap — `_make_gate`.** When enabled, add a per-strategy ceiling: that strategy's own
   `deployed + prospective_value ≤ allocated_equity(name)`. This stops an overweight strategy from
   growing further at entry time (the passive half of soft mode). Disabled ⇒ unchanged.
4. **Hard trims — new step in `tick_all`.** After the strategy loop, if
   `settings.enabled and mode == "hard"`: call `self._rebalancer.evaluate(...)`; for each
   `TrimAction`, place a **reduce-only market SELL** of `qty` via `self._broker` and shrink the
   stored `OpenPosition.qty` (the remainder keeps its existing stop, managed normally next tick).
   Then `state.save_rebalance_state` with `last_rebalance_at = now`.

### 4.4 Safety gates (mandatory, enforced in `tick_all` before any trim)

- **Portfolio kill switch / circuit breaker:** if `self._portfolio_risk.state.kill_switch_active`
  → skip rebalancing entirely (no trims), `skipped_reason="portfolio kill switch"`.
- **Per-strategy kill switch:** never trim a strategy whose `RiskState.kill_switch_active` (its
  exposure is already frozen/being unwound by its own logic).
- **Never force entries:** rebalancing only ever *sells* (hard) or *shrinks future size* (soft). It
  never opens or enlarges a position.
- **Paper/live gate:** hard trims route through the same `self.mode` path as entries; in `live`,
  trims are real sell orders subject to the existing live eligibility. Default config ships
  `enabled=false, mode="soft"` so nothing changes until the user opts in.
- **Telemetry:** every evaluation (ran or skipped) is logged — allocations, drift, mode, actions,
  skip reasons — so the decision is always auditable.

### 4.5 Telemetry (`telemetry.py`)

Add a `rebalance_events` table + `record_rebalance(event)` and `recent_rebalance(limit)`. One row
per `evaluate()` call: timestamp, mode, ran, skipped_reason, JSON of allocations and trims. Bounded
by the same retention pattern as `cycle_records`.

### 4.6 API (`web.py`)

- `GET  /api/rebalance/status` — current allocations (target/actual/drift), mode, `enabled`,
  `last_rebalance_at`, next-eligible time, last skip reason.
- `GET  /api/rebalance/settings` / `POST /api/rebalance/settings` — read/update `RebalanceSettings`
  (validated).
- `GET  /api/rebalance/targets` / `POST /api/rebalance/targets` — read/update target weights
  (validated: each ∈[0,1], sum ≤ 1.0, known strategies).
- `POST /api/rebalance/run` — manual trigger; runs `evaluate` immediately, still honoring all
  guards + paper/live gate; returns the `RebalanceResult`.

### 4.7 Dashboard (`frontend/`)

A **Rebalance** panel (new section on the existing dashboard/Settings, reusing current components):

- **Allocation table** — per strategy: target vs actual weight, drift, with a bar showing
  over/under-weight; row highlighted when `|drift| > threshold`.
- **Controls** — enable toggle, mode toggle (soft/hard), threshold + min-interval + fee inputs,
  editable target weights with live "sums to X%" validation.
- **Status** — last rebalance time, next eligible, last skip reason, and a **"Rebalance now"**
  button (calls `POST /api/rebalance/run`), disabled in soft mode / when not enabled.

## 5. Testing strategy (TDD)

Pure-logic unit tests (no IO) cover the bulk:

- `compute_allocations` / `allocated_equity` math (incl. missing-target equal-weight fallback).
- `detect_drift` threshold boundaries.
- `plan_trims` minimal-trim math (trims to just under `target + threshold`).
- Each guard independently: vol skip, min-interval, fee/benefit skip, correlation-cluster offset.
- Soft sizing: a strategy sizes off `allocated_equity`, not total.
- Soft cap in `_make_gate`: overweight strategy blocked from growing.
- Safety: portfolio kill switch suppresses all trims; per-strategy kill switch skips that strategy;
  rebalancing never produces a buy/entry.
- Paper/live gate: hard trim is a sell on the configured mode path.
- Persistence round-trips (targets, settings, rebalance state) and telemetry recording.

Integration tests drive `PortfolioSupervisor.tick_all` with `FakeBroker`/`FakeData` (as in
`tests/test_orchestrator.py`) to verify end-to-end soft sizing and a hard-mode trim, plus the
`enabled=false` regression that current behavior is unchanged.

## 6. Out of scope (YAGNI)

- Full correlation-matrix / risk-parity optimization.
- Rebalancing on a separate thread/scheduler (we run inside `tick_all`).
- Cross-strategy capital *transfer* accounting beyond sizing budgets (we trim/throttle; we don't
  bookkeep an internal ledger).
- Tax-lot / wash-sale logic.

## 7. Rollout

Ships **off** (`enabled=false`, `mode="soft"`). User enables soft mode first (sizing-only, zero
sell risk), observes the allocation table, then opts into hard mode when comfortable. Docker rebuild
+ restart of `swingbot` per the standing rule on every code change.
