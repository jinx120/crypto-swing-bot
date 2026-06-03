# Sub-project B — Phase 2: Auto-Strategy Discovery

**Status:** Designed & ready to plan.
**Date:** 2026-06-03
**Depends on:** Phase 1 deep archive (`CandleStore` populated with ~2y history), the existing
`run_backtest` engine, `presets.build_candidates` / `strategy_search`, the live
`ConfluenceEngine` / `RegimeFilter`, and Sub-project A's `/api/universe` + `/api/watchlist`.

---

## Background & motivation

Phase 1 gave the bot deep, stable history so backtests are meaningful instead of noise on
~5 days. Phase 2 is the payoff: **automatically sweep candidate strategies across the whole
coin universe, rank them on real history, surface which ones are "eligible now," and let the
user arm a winner in one click** — turning the archive into actionable discovery.

The building blocks already exist and are reused, not replaced:
- `presets.build_candidates(symbol, risk, style)` produces the per-symbol candidate profiles.
- `strategy_search` already does build → `run_backtest` → rank-by-expectancy for **one** symbol.
  Discovery generalizes this across the universe and adds caching + live "now" state.
- `run_backtest` is lookahead-safe and shares `exits` with live trading (backtest↔live parity).
- `ConfluenceEngine` + `RegimeFilter` evaluate the live signal/regime state on the latest bars.

### Key decisions (from brainstorming, 2026-06-03)

1. **Sweep scope = full universe × archetypes** at a fixed `swing` style. Comprehensive
   (every curated Alpaca USD pair × the 5 non-AI archetypes), so it leans on a background job
   + cache rather than per-request compute.
2. **"Eligible now" = good history + regime OK.** A row is eligible when it ranked well
   historically **and** the regime filter currently permits entry. Whether the confluence
   *fires* on the latest bar is computed and shown as a **non-gating** info indicator.
3. **Coverage-derived scenario windows.** Selectable windows are computed from what the store
   actually holds (`Full history` / `Last 1y` / `Last 90d` / `Last 30d`), so they always have
   data. Named historical crises (2022 bear, Covid) are **not** hardcoded; they surface
   automatically once deeper CSV dumps extend coverage (a documented follow-on, not built now).
4. **One-click arm = save + arm** (paper-trades immediately). Everything here is Alpaca
   **paper**; `live_eligible` is only a status marker today (`supervisor.py:228` surfaces it but
   it does **not** gate order placement), so arming a strategy is sufficient to start paper
   trades. We set `live_eligible` ON for UI clarity. No real-money live gating is built in
   Phase 2 — the goal is to prove the paper-trade loop end to end.

### Execution model: background recompute + cache (chosen)

A full-universe sweep is ~30–50 coins × 6 archetypes ≈ hundreds of heavy backtests over the
deep archive — minutes of compute. Options weighed:

- **(A) Background recompute + cached result — CHOSEN.** A `DiscoveryEngine` runs the sweep in
  a daemon thread (mirrors the Phase 1 archive-backfill pattern in `web.py`), writes ranked
  results to a JSON cache; `GET /api/discovery` returns the cache + freshness/status, and
  `POST /api/discovery/refresh` triggers a recompute. Non-blocking and controllable.
- (B) On-demand synchronous compute — simplest, but blocks the HTTP request for minutes and
  risks timeouts. **Rejected.**
- (C) Timer-only precompute — no manual trigger, stale until next tick. **Rejected** (a timer
  can be layered onto (A) later if wanted).

---

## Architecture & components

All new backend code lives in `src/swingbot/discovery.py` (the engine, no web/thread concerns)
plus thin wiring in `web.py`. The UI adds one `Discover.jsx` panel + a nav tab, following the
existing `PresetGallery` / `StrategyManager` component patterns.

### 1. `DiscoveryEngine` (`src/swingbot/discovery.py`)

The sweep/rank core. Pure functions over an injected `market` (so it's testable against an
in-memory `CandleStore`, no network).

- **`sweep(market, symbols, window=None, style="swing", max_symbols=50) -> list[Row]`**
  - For each symbol (capped at `max_symbols`):
    - **Load the candle df once** for the symbol's timeframe (from the `swing` style → `15m`)
      via the same `market.get` path `strategy_search` uses, but with a **deep lookback** so the
      whole archive is in play — not `strategy_search`'s `lookback=1000`, which would defeat the
      deep store. Use a large bound (default `lookback=100_000`, ≈ 2.8y of 15m) and then slice to
      `window`. This avoids `backtest_profile`'s per-candidate refetch — all archetypes for a
      symbol run against one loaded df.
    - For each non-AI archetype, build its profile (reusing `presets._profile_for` /
      `build_candidates` shapes) and run `run_backtest(df, profile, benchmark_df)`.
    - The benchmark df (`BTC/USD`, same timeframe/window) is loaded **once** and reused for any
      `relative_strength` candidate.
    - Compute `eligible_now` and `fires_now` (see below) from the tail of the same df.
  - Symbols with `< 30` bars (`InsufficientData`) are skipped with a reason; one failing
    symbol/candidate never aborts the sweep (per-row `error`, like `strategy_search.search`).
- **Row shape:**
  `{symbol, archetype, label, profile, metrics: {n_trades, win_rate, expectancy,
  profit_factor, max_drawdown, total_return, avg_win, avg_loss}, eligible_now, fires_now,
  regime, error}` (metrics via the existing `metrics_dict` serializer).
- **Ranking:** rows sorted by `(expectancy, win_rate, n_trades)` descending — the same key as
  `strategy_search.search` — across all `(symbol, archetype)` rows. Failed rows sort last.

### 2. Eligibility & "now" state

- `good_history(metrics) := n_trades >= MIN_TRADES and expectancy > 0 and profit_factor > 1`
  with `MIN_TRADES = 20` (a module constant; deep history makes this attainable).
- `regime_permits` — build a `RegimeFilter(profile)`, evaluate it on a `MarketContext` whose
  `candles` is the tail of the loaded df, and call `permits_entry(reg.regime)`.
- `eligible_now := good_history AND regime_permits`.
- `fires_now` — build a `ConfluenceEngine(build_signals(profile), profile)`, evaluate it on the
  same latest `MarketContext`, and take `conf.passed`. **Informational only**, never gates
  eligibility (per decision 2). `regime` (the evaluated regime label) is included for display.

### 3. Scenario windows (`windows_for`)

- `windows_for(coverage) -> list[{key, label, start_ms, end_ms}]` derives selectable windows
  from a `CandleStore.coverage` result (`min_ts` / `max_ts`). Always includes `full`; adds
  `last_30d`, `last_90d`, `last_1y` only when the covered span is long enough to be meaningful.
- A window is applied by slicing the loaded df on `ts` before backtesting. `full`/`None` means
  the entire loaded df.
- Coverage is read for a representative symbol (the universe's first covered symbol, or
  `BTC/USD`); the same window set applies to the whole sweep for consistency.

### 4. Caching & cost control

- Results are cached to a JSON file at `<SWINGBOT_DATA_DIR or ~/.swingbot>/discovery.json`:
  `{computed_at: epoch_s, window: key, scope, params, rows: [...]}`.
- The cache is loaded on startup (best-effort; a missing/corrupt file → empty, status `idle`)
  and is what `GET /api/discovery` returns.
- `status` is one of `idle` | `computing`; a refresh sets `computing`, the daemon thread writes
  the cache and flips back to `idle` (or `idle` with an `error` string on failure).
- **Bounds:** `max_symbols` (default 50); one df load per symbol; the sweep runs on a daemon
  thread, entirely off the live trading loop, so a long sweep never blocks trading or requests.

### 5. API (token-guarded, mirrors the Phase 1 archive endpoints in `web.py`)

- `GET /api/discovery` → `{computed_at, window, scope, status, error, rows[]}` from the cache.
- `GET /api/discovery/windows` → coverage-derived window options (`windows_for`).
- `POST /api/discovery/refresh` (body `{window?: str, scope?: "universe"|"watchlist",
  max_symbols?: int}`) → if a sweep is already `computing`, return `{started:false,
  status:"computing"}`; otherwise resolve the symbol list (universe via `/api/universe`'s source
  or watchlist via `profiles.get_watchlist()`), set `status=computing`, kick a daemon thread,
  return `{started:true}`. Failures are caught and logged; never touch live trading.
- `POST /api/discovery/arm` (body `{symbol, archetype, window?}`) → reconstruct that row's
  profile deterministically (same `_profile_for` inputs), save it under a generated name
  (`disc-<symbol-slug>-<archetype>`, e.g. `disc-btcusd-aggressive`), then `profiles.arm(name)`
  and `set_live_eligible(name, True)`, and `controller.reload()` (mirroring the existing arm
  endpoint). Returns `{ok:true, name}`. One click → the strategy is armed and paper-trades.

Wiring: `create_app(...)` gains an optional `discovery` engine handle and a
`app.state.discovery_cache` (loaded on startup), exactly mirroring how `backfiller` /
`app.state.archive_config` are threaded through today.

### 6. UI — `Discover` panel (`frontend/src/components/Discover.jsx` + nav tab)

- **Controls row:** a window `<select>` (from `GET /api/discovery/windows`), a scope toggle
  (Universe / Watchlist), and a **Refresh** button. Shows `computing…` while a sweep runs and a
  freshness line (`computed 4m ago`) from `computed_at`; polls `GET /api/discovery` while
  `computing`.
- **Ranked list, grouped by coin:** each row shows the archetype, `n_trades`, win rate,
  expectancy, profit factor, and max drawdown; an **eligible-now badge** (regime OK + good
  history) and a small **fires-now** dot; and a one-click **Arm** button (calls
  `POST /api/discovery/arm`, then surfaces the new strategy in the manager).
- **Metric coloring:** simple buckets (expectancy / profit-factor tiers → color classes) for
  scan-ability. No charts.
- New API client methods in `frontend/src/api.js`: `getDiscovery`, `getDiscoveryWindows`,
  `refreshDiscovery`, `armDiscovery`.

### 7. Error handling

- Per-row isolation: a candidate that raises is captured as `metrics:null, error:str` and the
  sweep continues (same contract as `strategy_search.search`).
- `InsufficientData` symbols are skipped with a reason, not fatal.
- A sweep-level failure is caught in the daemon thread, logged, and recorded as the cache's
  `error` with `status` returned to `idle`; **it never touches the live trading loop.**
- Endpoints return 503 if discovery isn't configured on the server (mirrors archive backfill).

### 8. Testing (no network, mirrors existing style)

- `DiscoveryEngine.sweep` over a seeded in-memory `CandleStore`: ranking order (expectancy
  desc), `good_history` / `eligible_now` predicate, `fires_now` computed independently of
  eligibility, per-row error isolation (one bad symbol doesn't abort), `max_symbols` cap, and
  single-df-load reuse for multi-archetype symbols.
- `windows_for`: coverage math (which windows appear for short vs long coverage; slicing
  boundaries).
- `POST /api/discovery/arm`: saves a profile that round-trips through `StrategyProfile.from_dict`
  and arms it (the armed set + `live_eligible` flag reflect the new name).
- `GET /api/discovery` / `refresh`: cache read, `computing` guard (a second refresh while
  computing returns `started:false`).
- Full suite stays green (currently `235 passed, 5 skipped`) plus these new tests.

### 9. Success criteria

- `POST /api/discovery/refresh` sweeps the universe over the deep archive (off the trading
  thread) and `GET /api/discovery` returns coins ranked by expectancy with `eligible_now` flags
  and a `computed_at`.
- The Discover panel lists ranked strategies grouped by coin with eligible-now badges, and a
  **one-click Arm makes a strategy appear armed in the manager and place paper orders** on its
  next signal firing.
- Re-opening the app shows the cached results immediately without a recompute.
- A sweep that hits a bad/insufficient symbol still returns ranked results for the rest.

### Out of scope for Phase 2

- Per-row equity-curve chart, Sharpe, and full trade table (the outline's richer btfdbot
  treatments) — deferred to keep Phase 2 focused on proving the loop.
- Hardcoded historical-crisis windows (2022 bear / Covid) — they appear automatically once
  deeper CSV dumps extend coverage.
- Timer-based automatic recompute — manual refresh only for now (a timer can layer onto the
  background-job model later).
- Real-money live gating — everything stays Alpaca paper; `live_eligible` remains a status
  marker.
