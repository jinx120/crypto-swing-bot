# Multi-Asset Concurrent Trading + Dashboard Stabilization — Design

_Date: 2026-05-31. Status: approved design, pre-implementation._

## 1. Summary

Today SwingBot trades **one** active strategy profile through **one** `Orchestrator`,
driven by `BotService` in a single background thread, with a single `active` profile
pointer and single-row position/risk state. This design extends it to **trade several
assets concurrently**, each with its own strategy, under a shared-capital portfolio
risk layer — and folds in fixes for the dashboard bugs that currently break the UI
(misplaced tooltips, null crashes, stale ticker, opaque backend-unreachable failures).

The unit of concurrency is the **symbol**: an Alpaca account holds exactly one position
per symbol, so "multiple strategies at once" means a portfolio of distinct symbols, one
strategy each. Two strategies competing on the same symbol is explicitly out of scope.

## 2. Goals / Non-Goals

### Goals
- Run up to ~15 strategies concurrently, one per distinct symbol, in paper or live mode.
- Shared-pool capital with portfolio-level caps and a portfolio-wide kill switch.
- Dashboard that shows multiple assets/charts at once and reflects state changes promptly.
- Stay within Alpaca rate limits regardless of how many symbols are armed.
- Fix the current breakage: tooltip placement, "value is null" crashes, stale ticker,
  silent backend-unreachable failures.

### Non-Goals
- Multiple strategies trading the **same** symbol (broker can't represent it).
- Per-strategy paper/live mixing on one account (paper vs live are different key sets;
  mode stays global).
- Shorting / margin (unchanged: long-only spot).
- Deep historical backtesting platform / data archive (separate roadmap item, §10).

## 3. Constraints & Key Facts

- **One position per symbol per Alpaca account.** Symbol is the concurrency unit.
- **Mode is global.** Paper vs live use different Alpaca credentials, so the whole bot
  is paper or live at once.
- **Swing cadence (~60s).** Sequential ticking of ≤15 symbols from a warm cache costs
  milliseconds; parallelism is unnecessary.
- **`ERR_NAME_NOT_RESOLVED` is environmental.** The `/api/*` calls are relative, so this
  is a DNS failure on the page's own host (loading the dashboard from a hostname that no
  longer resolves — e.g. a stale Tailscale name or a downed container). Code can only
  surface it clearly; the fix is to load the UI from a resolvable host or via the Vite
  `/api` proxy. Documented here so it isn't mistaken for a code defect.

## 4. Architecture

### 4.1 Approach (chosen: single supervisor loop)

A single **`PortfolioSupervisor`** thread iterates the armed strategies each cycle and
ticks each `Orchestrator` sequentially. Portfolio capital/risk accounting lives in one
**single-writer** object — no locks, no races on the money-critical path. This is the
smallest leap from the existing `tick()` model and reuses `Orchestrator` and
`RiskManager` almost verbatim.

Rejected alternatives: (A) one thread per strategy + lock-guarded shared risk — makes
the correctness-critical accounting a multi-writer hot spot; (C) N independent
`BotService`s coordinated via SQLite — race-prone, hard to reason about.

```
PortfolioSupervisor (one loop thread)
 ├─ armed: [ (profile, Orchestrator, RiskManager), ... ]   # one per symbol
 ├─ PortfolioRiskManager   (single-writer: global caps + portfolio kill switch)
 ├─ shared MarketData (cache-backed)   ← orchestrators read prices/candles here
 └─ each cycle:
      1. batch-refresh cache for ALL armed symbols (grouped by timeframe)
      2. for each armed strategy (deterministic priority order — see below): orch.tick()
           entry allowed only if strategy RiskManager AND PortfolioRiskManager approve
      3. recompute + store each strategy's signal snapshot (for the API to read)
```

### 4.2 `PortfolioSupervisor` (new — replaces single-strategy `BotService`)

Responsibilities:
- Own the armed set; build/teardown an `Orchestrator` + `RiskManager` per armed profile.
- Drive the per-cycle loop above in one thread.
- Hold the shared `MarketData` and `PortfolioRiskManager`.
- Cache per-strategy snapshots + portfolio summary for the API (so endpoints never call
  Alpaca).
- Expose portfolio controls (halt/reset/pause/resume/mode) and per-strategy
  controls (flatten/disarm).

`BotController` Protocol is extended (or superseded by a `PortfolioController` Protocol)
to cover the new surface; the FastAPI layer depends only on the Protocol.

### 4.3 `PortfolioRiskManager` (new — the heart of the rearchitecture)

Single-writer object, checked **before any strategy opens a position**, layered on top
of each strategy's existing `RiskManager`. Enforces:

- **Max concurrent positions** — global cap on the number of *open positions* across all
  symbols at once. This is distinct from how many strategies are **armed**: you may arm up
  to ~15, but only `max_concurrent` of them can hold a position simultaneously (a
  diversification/exposure safety limit). Set it equal to the armed count to remove the cap.
- **Max total deployed** — `sum(open position values) ≤ max_total_deployed_frac × equity`
  (default `0.80`). Each strategy still sizes off total equity; if the new position would
  breach the cap, the entry is **rejected** for this cycle (simplest, safest; clamping
  can come later).
- **Portfolio daily-loss kill switch** — aggregate realized PnL across all strategies for
  the UTC day; trips a global halt on new entries. Open positions are still managed and
  allowed to exit.

Per-strategy kill switches (consecutive losses, post-stop cooldown) are unchanged and sit
underneath the portfolio gate. An entry requires approval from **both** layers.

**Tick priority order.** When `max_concurrent` or the deployed cap is the binding
constraint, the order strategies are ticked decides who gets the remaining slot. Order is
**deterministic**: armed strategies are ticked sorted by profile name (stable, predictable,
and easy to reason about in tests). A future enhancement could rank by live signal score;
out of scope here.

Defaults (configurable via portfolio settings): `max_concurrent = 5`,
`max_total_deployed_frac = 0.80`, `portfolio_daily_loss_limit_pct = 0.08`.

### 4.4 Entry decision flow (per strategy, per cycle)

```
if supervisor.paused or strategy.paused: skip
if strategy already has a position (broker truth): manage/exit only
if strategy.RiskManager.check_can_enter(...) not approved: skip
if PortfolioRiskManager.check_can_enter(symbol, equity, prospective_value) not approved: skip
if mode == live and not strategy.live_eligible: skip   # paper still trades
... existing regime gate + confluence + sizing + ATR checks ...
open position; PortfolioRiskManager.on_position_opened(...)
```

On close, both `RiskManager.on_trade_closed` and
`PortfolioRiskManager.on_trade_closed` update their day PnL / counters.

## 5. State & Persistence Model

- **`StateStore`** — change single-row position (`id=1`) to **per-symbol** position rows
  (PK = symbol), plus **per-strategy** risk-state rows (PK = profile name), plus **one**
  `portfolio_risk_state` row. Add a one-time migration that moves any existing `id=1`
  position + risk row into the new keyed rows so live single-asset state is not lost.
- **`ProfileStore`** — replace the single `active` meta pointer with:
  - an **armed set** (table of armed profile names), and
  - a per-profile **`live_eligible`** boolean.
  Migration: on first run, if an old `active` value exists and the armed set is empty,
  seed the armed set with it.
- **Portfolio settings** — stored in `ProfileStore.meta` (or a small `portfolio_settings`
  row): `max_concurrent`, `max_total_deployed_frac`, `portfolio_daily_loss_limit_pct`.

## 6. Data Layer & Rate Limits

The supervisor becomes the **only** component that talks to Alpaca; everything else reads
the cache.

- **Batched warming.** Each cycle, group armed symbols by timeframe and issue **one**
  `CryptoBarsRequest(symbol_or_symbols=[…])` per distinct timeframe, plus **one**
  multi-symbol latest-trade request. API calls scale with number of timeframes, not number
  of symbols — a handful per 60s cycle for 3 or 15 symbols. (Extends the existing
  `CandlePoller`/`MarketData`; `AlpacaData.get_candles`/`get_latest_price` gain
  multi-symbol forms.)
- **Orchestrators never call Alpaca directly** — they read prices/candles from the warm
  `MarketData` cache, decoupling tick rate from API rate.
- **`/api/state` served from precomputed snapshots.** Today it fetches candles on every
  request to compute the signal snapshot — with 2s polling that is a rate-limit and lag
  source. The supervisor computes snapshots once per cycle and stores them; the endpoint
  just serializes. Primary cure for "UI lagging behind."
- **Chart fetch coalescing.** `/api/candles` stays cache-backed; armed symbols are already
  warm. Add single-flight so concurrent identical fetches share one upstream call.
  Mini-charts default to no indicators to keep many chart instances light.
- **Polling cadence.** `/api/state` carries everything the dashboard needs (portfolio +
  per-strategy list incl. snapshots and positions). The separate 2s journal/metrics polls
  drop to a slower cadence.

## 7. API Surface

Token rules unchanged (reads open, writes require `X-Token`).

- `GET /api/state` →
  `{ portfolio: {mode, running, paused, equity, deployed, deployed_frac, open_positions,
    day_pnl, kill_switch:{active,reason}}, strategies: [ {name, symbol, running,
    live_eligible, snapshot, position, risk:{kill_switch, consecutive_losses}}, … ] }`
  — cheap, cached.
- `GET /api/strategies` → list of profiles with `{name, symbol, armed, live_eligible}`.
- `POST /api/strategies/arm` `{name}` / `POST /api/strategies/disarm` `{name}`.
- `POST /api/strategies/live-eligible` `{name, eligible}`.
- `GET/PUT /api/portfolio/settings` → `{max_concurrent, max_total_deployed_frac,
  portfolio_daily_loss_limit_pct}`.
- Controls: `POST /api/control/{halt|reset|pause|resume|mode}` act at **portfolio** level;
  add `POST /api/control/{strategy}/flatten` and the disarm route above for per-strategy.
- `GET /api/journal` / `GET /api/metrics` → aggregate across strategies, with optional
  `?strategy=<name>` filter.
- Unchanged in shape: `GET /api/candles`, `GET /api/presets`,
  `POST /api/strategy/build`, `POST /api/strategy/backtest`.

`go-live` (mode → live) still requires the **global graduation gate** (≥30 aggregate
paper trades + positive expectancy) to pass; individual strategies additionally require
their `live_eligible` flag to be on before they trade live.

## 8. Frontend

- **Dashboard = portfolio summary banner + responsive grid of per-strategy cards.**
  Banner: mode, equity, total deployed, # open positions, portfolio day PnL, portfolio
  kill switch. Each card: symbol, a mini chart, signal score/regime, position, and
  per-strategy flatten/disarm. This is the "multiple charts / multiple assets at once."
- **Reactivity (stale-ticker fix).** Every card is **keyed by symbol**; `ChartPanel`
  takes `symbol` as a required prop and refetches on change. Remove the `meta.symbol`
  local-cache fallback that currently lets an old ticker linger. State flows one way from
  the server, so switching strategies cannot leave stale tickers in multiple spots.
- **Strategy page.** Arm/disarm + live-eligible toggles per profile, plus portfolio-caps
  settings. Presets + guided builder unchanged.
- **Chart performance.** Cap simultaneous full-feature charts; mini-charts render fewer
  features and lazy-mount when their card is visible.

### 8.1 Bug fixes (folded in)

- **Tooltips in random spots** — `Hint` renders its tip via `createPortal` to
  `document.body`, escaping the `backdrop-filter` containing-block trap (a `backdrop-filter`
  ancestor becomes the containing block for `position: fixed` children, so viewport-coord
  math and render currently disagree). Keep the existing viewport-coordinate computation.
- **"value is null" crashes** — guard chart `setData` against empty/None data, guard
  `Date.parse` NaN markers, and render an empty-state for zero candles instead of throwing.
- **Bad symbol** — on empty data show "no data — check symbol (Alpaca uses `BTC/USD`, not
  `USDT`)" rather than crashing. Optionally validate `BASE/QUOTE` shape on input.
- **Backend unreachable** (`ERR_NAME_NOT_RESOLVED`) — show a clear "Cannot reach backend"
  banner when `/api/*` requests fail, instead of silent nulls. (DNS itself is
  environmental; see §3.)

## 9. Phasing (implementation order)

- **Phase 0 — Frontend stabilization.** Tooltip portal, null-safety, bad-symbol guard,
  backend-unreachable banner. Independent and cheap; unbreaks today's UI first.
- **Phase 1 — Backend concurrency core.** `PortfolioSupervisor`, `PortfolioRiskManager`,
  per-symbol `StateStore`, armed-set `ProfileStore`, batched shared data + multi-symbol
  `AlpacaData`. Paper-only, fully unit-tested.
- **Phase 2 — API surface.** New `/api/state` shape, arming endpoints, portfolio settings,
  aggregate journal/metrics, portfolio-level controls.
- **Phase 3 — Frontend multi-chart dashboard.** Portfolio banner + per-strategy card grid,
  arm/disarm + live-eligible UI, reactivity fix (consumes Phase 2).
- **Phase 4 — Live-eligibility gating.** Enforce `live_eligible` + portfolio kill-switch
  surfacing + go-live flow across the portfolio.

## 10. Testing

Reuse existing `FakeData`/`FakeBroker` fakes. New/extended tests:
- `PortfolioRiskManager`: max-concurrent, max-deployed, portfolio daily-loss kill switch;
  both-layers-must-approve entry gating.
- `PortfolioSupervisor`: sequential tick across multiple fake strategies; only-one cycle
  of data fetch; snapshot caching; per-strategy flatten/disarm.
- `StateStore`: per-symbol position roundtrip; per-strategy + portfolio risk-state
  roundtrip; migration from single-row.
- `ProfileStore`: armed-set + `live_eligible`; migration from `active`.
- Web: new endpoints + token rules; `/api/state` shape.
- Keep the existing suite (160 passed / 4 skipped) green.

## 11. Future directions (out of scope here)

- Deep historical data archive + backtesting platform (existing roadmap, §9 of the
  strategy-presets-builder design): a `Backfiller` beside the poller, a `source` column on
  `bars`, pluggable `MarketDataProvider`s. The portfolio supervisor and shared cache here
  are compatible with that work.
- Capital **clamping** (size-down to fit the deployed cap) instead of reject.
- Per-strategy capital budgets (the "per-strategy budget" capital model) if shared-pool
  contention proves limiting.
