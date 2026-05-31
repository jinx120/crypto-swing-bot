# Strategy Presets + Backtest-Driven Guided Builder — Design

**Date:** 2026-05-31
**Status:** Approved (brainstorming) — ready for implementation plan
**Depends on:** existing `run_backtest` engine, `MarketData`/`CandleStore` (added 2026-05-31), `ProfileStore`, `StrategyProfile`.

## 1. Problem & Goal

Today a runnable strategy only comes from the **detailed parameter form** (`frontend/src/pages/Strategy.jsx`) — ~25 fields. Even though it is a structured form (not raw JSON), it asks the user to understand confluence weights, ATR multiples, regime periods, etc. The user wants it to be **as simple as choosing a coin and letting data analysis configure the rest**, plus a set of **ready-made strategies they can run immediately**.

Goal: add two low-effort paths to a runnable `StrategyProfile`, both feeding the existing form (kept as the power-user layer):

1. **Preset library** — curated, named archetypes, runnable instantly or backtestable.
2. **Guided builder** — pick *Coin + Risk + Style + AI toggle*; the server runs a **bounded backtest search** over the coin's real recent candles, ranks candidates by performance, and recommends the winner with evidence.

Non-goal (this iteration): a full backtesting platform or parameter optimizer — see §9 Future Directions, which this design is explicitly built to seed.

## 2. Decisions (from brainstorming)

| Fork | Decision |
|------|----------|
| How params are chosen | **Backtest-driven pick** — fetch the coin's recent candles, run candidate strategies through the existing `run_backtest`, rank by performance. |
| User-facing knobs | **Coin + Risk + Style + "Use AI (Kronos)" toggle**; signals/thresholds/exits auto-searched within those constraints. |
| Execution model | **Synchronous, bounded** search (~4–6 candidates; 2–3 when AI on). FastAPI sync endpoints run in a threadpool, so the event loop is not blocked. No job system. |
| Page structure | **3 tiers** — Preset gallery + Guided builder both produce a profile that drops into the existing **detailed form** for review/tweak → Save + Set active. Nothing removed. |
| Archetypes | Conservative / Balanced / Aggressive / AI-Kronos. |
| Styles | Scalp / Swing / Position → 5m / 15m / 1h (+ hold/regime/window scaling). |

## 3. Architecture

```
Frontend Strategy.jsx (3 tiers)
  Tier 1 Preset gallery ──GET /api/presets──────────┐
  Tier 2 Guided builder ─POST /api/strategy/build──┐ │
  Tier 3 Detailed form (existing) ◄── prefilled ───┘ │
        │ Save (existing /api/profiles)              │
        ▼                                            ▼
  ProfileStore (SQLite)                       web.py endpoints
                                                     │
                         ┌───────────────────────────┴───────────┐
                         ▼                                        ▼
                  swingbot/presets.py                  swingbot/strategy_search.py
                  ARCHETYPES, build_candidates()        backtest_profile(), search()
                                                              │
                                       ┌──────────────────────┼─────────────┐
                                       ▼                      ▼             ▼
                                 MarketData            run_backtest()    Metrics
                                 (candles, cached)     (existing)       (existing)
```

## 4. Backend components

### 4.1 `swingbot/presets.py` (new)
- `ARCHETYPES: list[Archetype]` — curated base strategies, each: `key`, `name`, `description`, `signals` used, and a builder that emits a `StrategyProfile` dict given (symbol, risk, style, ai). Set:
  - **Conservative** — oversold (RSI dip) + trend gate; tight risk, higher entry threshold.
  - **Balanced** — oversold + VWAP.
  - **Aggressive** — oversold + VWAP + relative-strength; looser threshold, wider targets.
  - **AI-Kronos** — Balanced base + `kronos_forecast` signal.
- `build_candidates(symbol, risk, style, ai) -> list[Candidate]` where `Candidate = {label, profile}`. Returns a **bounded** set: the archetypes appropriate to the knobs, each materialized with the risk/style mapping, plus 1–2 threshold variants. Cap: **6** candidates, **3** when `ai=True`. If `ai=True`, the AI-Kronos archetype is included; otherwise it is excluded.
- Pure functions; no I/O. Easy to unit-test.

**Risk mapping** (applied to every candidate):

| Risk | risk_per_trade | stop_atr_mult | take_profit_atr_mult | entry_threshold | daily_loss_limit_pct | max_consecutive_losses |
|------|---------------|---------------|----------------------|-----------------|----------------------|------------------------|
| Conservative | 0.005 | 1.2 | 2.4 | 0.45 | 0.03 | 3 |
| Balanced | 0.01 | 1.5 | 2.0 | 0.35 | 0.05 | 4 |
| Aggressive | 0.02 | 2.0 | 3.0 | 0.30 | 0.08 | 5 |

**Style mapping**:

| Style | timeframe | max_hold_bars | regime_ma_period | vwap_window | rs_lookback | cooldown_minutes |
|-------|-----------|---------------|------------------|-------------|-------------|------------------|
| Scalp | 5m | 24 | 50 | 48 | 48 | 30 |
| Swing | 15m | 32 | 50 | 96 | 96 | 60 |
| Position | 1h | 24 | 100 | 96 | 96 | 240 |

(Values are starting points; tunable during implementation. `benchmark_symbol` defaults BTC/USD; `atr_period` 14.)

### 4.2 `swingbot/strategy_search.py` (new)
- `backtest_profile(market, profile_dict, lookback=1000) -> Metrics` — the reusable primitive. Fetch `lookback` candles for `profile.symbol`/`timeframe` via `MarketData.get(...)`; if the profile enables relative-strength, also fetch the benchmark; run the existing `run_backtest(df, profile, benchmark_df)`; return its `Metrics`. Raises a typed error if too few candles or no market access.
- `search(market, symbol, risk, style, ai) -> SearchResult` —
  1. `candidates = build_candidates(...)`.
  2. For each, call `backtest_profile`; capture `Metrics` or an `{error, reason}` (e.g. Kronos not installed, insufficient data). One failure never aborts the search.
  3. Rank successful candidates by **expectancy** desc; tie-break **win_rate**, then **n_trades**. Flag the top as `recommended`.
  4. Return `{symbol, risk, style, ai, results:[{label, profile, metrics|error, recommended}]}`.
- Compute is bounded by candidate cap × lookback cap.

### 4.3 `web.py` endpoints
- `GET /api/presets` (read-only) → archetype cards: `[{key, name, description, signals}]`.
- `POST /api/strategy/backtest` (token) → body `{profile}` → `{metrics}` (single run). Powers preset "Backtest" + a form "Test this" button.
- `POST /api/strategy/build` (token) → body `{symbol, risk, style, ai}` → `SearchResult`. Synchronous.
- All three are **non-persisting**. Saving remains the existing `POST /api/profiles` after the user reviews in the form.
- `create_app` gains a `market=` dependency (already added) and a `presets`/`search` wiring; endpoints return `400` with a clear message when `market` can't fetch (no credentials).

## 5. Frontend (`Strategy.jsx` → 3 tiers)
- **Tier 1 Preset gallery** — cards from `/api/presets`. A small **coin dropdown** (curated common Alpaca pairs + free-text) sets the symbol applied when you click **Use** (loads the archetype into the form) or **Backtest** (calls `/api/strategy/backtest`, shows expectancy/win%/#trades inline on the card).
- **Tier 2 Guided builder** — dropdowns **Coin / Risk / Style** + **Use AI** toggle → **Build & backtest** → spinner → ranked **results table** (label · expectancy · win% · #trades · profit factor), recommended row highlighted, **Use this** per row loads that candidate's profile into the form.
- **Tier 3 Detailed form** — the existing form, now **pre-filled** by tier 1/2 via `parseProfile`, fully editable; existing Save + profile list (Set active / Delete) unchanged.

Data flow: tier 1/2 → set form state `f` → user reviews/tweaks → **Save** → (optional) **Set active** → Dashboard **Start**. The form remains the single write path, so validation and guardrails are unchanged.

`api.js` additions: `presets()`, `buildStrategy({symbol,risk,style,ai})`, `backtestProfile(profile)`.

## 6. Error handling
- No Alpaca credentials → `400 "set Alpaca credentials in Settings first"`; the builder surfaces it inline (it needs market data).
- Insufficient candles for a candidate → that row shows "insufficient data"; others still rank.
- `ai=true` but Kronos/torch not installed → that candidate row shows the import error reason; the rest of the search still completes and ranks.
- Per-candidate backtest exceptions are caught and rendered as error rows; the endpoint never 500s on a single bad candidate.
- Bounded compute (candidate cap + lookback cap) prevents runaway requests.

## 7. Testing
- `presets.py`: every (risk × style × ai) combo yields dicts that `StrategyProfile.from_dict` accepts; candidate counts within caps; AI absent when `ai=False`, present when `ai=True`.
- `strategy_search.py`: with a **fake `MarketData`** returning synthetic candles, ranking order is correct; a candidate whose backtest raises is captured as an error row (search still returns); `recommended` flags the best expectancy.
- `web.py`: `/api/presets` lists archetypes; `/api/strategy/build` returns ranked results + a recommended row (fake market); `/api/strategy/backtest` returns metrics; build without creds → 400; write endpoints require the token.
- Frontend: build succeeds; manual Playwright check of the 3 tiers + a build run.

## 8. Scope / YAGNI (this iteration)
- Synchronous only; **no** background job system.
- **Curated** candidate set, not a parameter sweep/optimizer — keeps each build to a few seconds.
- Presets are **templates** surfaced via API; not auto-dumped into `ProfileStore`.
- Backtests run over **recent** candles from the live cache (depth = lookback cap), not a deep historical archive (that is §9).
- Coin list = curated common pairs + free text, not an exhaustive Alpaca asset sync.

## 9. Future Directions (explicitly seeded by this design)

This iteration is deliberately the **kernel** of two larger systems the user wants next. The modules above are factored so these can grow without a rewrite.

### 9.1 Extensive backtesting platform (à la btfdbot.com/backtester)
A first-class backtesting workspace, separate from quick "build" search:
- **On-demand full backtests** over a chosen date range / deep history, with an **equity curve**, **drawdown chart**, **trade-by-trade table**, and full stats (Sharpe, Sortino, max DD, profit factor, exposure, CAGR).
- **Parameter optimization / sweeps** (grid or randomized) and **walk-forward / out-of-sample** validation to fight overfitting — a natural superset of today's curated `build_candidates` search.
- **Saved backtest runs** (persist `SearchResult`/full runs to SQLite) for comparison across strategies, assets, and timeframes; shareable result links.
- **Async job execution** with progress (the upgrade path noted in the execution-model fork) for long sweeps and heavy AI runs.
- *Seam in this design:* `strategy_search.backtest_profile()` is the single backtest entry point and `run_backtest()` already returns `(trades, Metrics)`; the platform consumes the same primitives, adding range selection, persistence, charts, and a job runner. The chart stack (Lightweight Charts, added 2026-05-31) already renders candles/markers and can render equity curves.

### 9.2 Persistent historical market-data archive + pluggable providers
Grow the candle store into a comprehensive historical database that becomes the backtest substrate:
- **Deep, continuous ingestion** — backfill jobs that page far back in history per (symbol, timeframe) and keep the archive current, well beyond the live read-through cache's recent window.
- **Pluggable data providers** behind the existing `MarketDataProvider` protocol (`src/swingbot/data/base.py`) — Alpaca today; future free/cheap sources (e.g. Binance, Kraken, CryptoCompare, CoinGecko, Polygon) added as new `*Data` classes implementing the same `get_candles`/`get_latest_price` interface. A provider registry + per-source rate-limit/backoff handling.
- **Multi-asset / multi-timeframe coverage** so strategy search and the backtesting platform can test across a large universe from local data, with no per-run API dependence.
- **Provenance + dedup** — the `CandleStore` schema (PK `symbol, timeframe, ts`, `INSERT OR REPLACE`) already dedups; add a `source` column and gap-detection/backfill to merge providers cleanly.
- *Seam in this design:* `CandleStore` (added 2026-05-31) is already symbol/timeframe/arbitrary-history capable; `MarketData` is the read-through ingestion layer. The archive extends both (a `Backfiller` alongside `CandlePoller`, schema add of `source`), and everything downstream (`backtest_profile`, `search`, the future platform) reads from the same store.

These are recorded as direction, not committed scope; the present iteration ships §§1–8 only.
