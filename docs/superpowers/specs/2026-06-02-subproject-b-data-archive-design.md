# Sub-project B — Historical Market-Data Archive (Phase 1) + Auto-Strategy Discovery (Phase 2)

**Status:** Phase 1 designed & ready to plan. Phase 2 outlined (own spec later).
**Date:** 2026-06-02
**Depends on:** existing `CandleStore` / `MarketData` / `MarketDataProvider` kernel; the
existing `run_backtest` engine and `presets.py` / `strategy_search.py`.

---

## Background & motivation

Sub-project B in the platform roadmap is "auto-strategy discovery": sweep candidate
strategies across the universe, backtest, rank, and surface an "eligible now" list with
one-click arm. **But ranking by backtest metrics is only as trustworthy as the history we
backtest on, and today that history is ~5 days.**

`~/.swingbot/candles.db` holds only ~524 bars of BTC/USD 15m (~5.5 days, recent and
downtrending). Every backtest — the preset builder, the guided builder, and any future
discovery sweep — runs on that one tiny window, so results are noise and bullish-long
strategies structurally lose. This was flagged as the highest-leverage next build.

**Therefore B is split into two phases with a clean seam:**

- **Phase 1 — Historical Market-Data Archive** *(this spec; the prerequisite)*. Give the bot
  deep, stable history so *all* backtesting becomes meaningful. Independently valuable.
- **Phase 2 — Auto-Strategy Discovery** *(outlined below; its own spec)*. The sweep / rank /
  arm engine, built on top of the archive.

### Key decisions (from brainstorming, 2026-06-02)

1. **Data layer = CCXT + CSV import.** CCXT is the unified API to 100+ exchanges behind one
   `fetch_ohlcv` call, so "multiple providers and more" becomes one pluggable adapter. A CSV
   importer ingests bulk dumps (binance.vision, cryptodatadownload.com) for anything else.
2. **Keep the existing backtest engine.** It is lookahead-safe (decides on the last closed
   bar, enters at the next bar's open — `backtest.py:81,99`), models fees + slippage, and
   **shares `exits.exit_decision`/`bracket_levels` with live trading** (backtest↔live parity).
   It has 19 unit + 4 integration tests passing. The flimsy part was always the *data*, not
   the engine. Adopting freqtrade/vectorbt would add troubleshooting surface (config, DSL,
   data formats, a second stack that can't trade Alpaca) — the opposite of the goal.
3. **No reference-parity check** (chosen for leanest scope; existing unit tests are deemed
   enough trust for a personal bot).
4. **Reuse the existing `CandleStore`** as the archive. No new schema; backfill upserts into
   the same `~/.swingbot/candles.db` that `MarketData` already serves.

### Why no engine changes are needed (verified)

`MarketData.get(symbol, timeframe, limit)` returns up to `limit` bars directly from
`CandleStore` (`market.py:59`), and with no `max_age` it does **not** refetch from Alpaca
(`_is_stale` returns False). `strategy_search` calls `market.get(..., lookback=1000)`. So the
"5-day cap" is purely a consequence of a shallow store. Backfill deep history into the store
and every backtest deepens transparently. **The archive is the only thing that needs building.**

---

## Phase 1 — Historical Market-Data Archive

### Goal

A `swingbot-backfill` path (CLI + endpoint) that populates `CandleStore` with deep history
(config-driven: which symbols, timeframes, how far back) from CCXT and/or CSV dumps, so
backtests run on real history instead of 5 days.

### Components

All new code lives under `src/swingbot/data/`, mirroring existing conventions
(`alpaca.py`, `store.py`, `market.py`).

#### 1. `CcxtProvider` (`data/ccxt_provider.py`)

- Implements the existing `MarketDataProvider` Protocol:
  `get_candles(self, symbol, timeframe, lookback) -> pd.DataFrame` (`data/base.py:9`), so it is
  a drop-in alongside `AlpacaData`.
- Adds a range-fetch method used by the backfiller:
  `get_candles_range(symbol, timeframe, start_ms, end_ms) -> pd.DataFrame`, paginating CCXT's
  `fetch_ohlcv(symbol, timeframe, since, limit)` forward until `end_ms` (CCXT returns ≤ ~1000
  bars/page). Honors `enableRateLimit`.
- **Symbol mapping.** The app speaks Alpaca symbols (`BTC/USD`). A small, config-driven map
  translates to the exchange's symbol: e.g. on Binance `BTC/USD → BTC/USDT` (USDT≈USD basis
  is < ~0.1%, fine as a swing backtest proxy); on Coinbase/Kraken `BTC/USD → BTC/USD` (exact).
  Default: a `quote_map` (`USD → USDT`) plus optional per-symbol overrides.
- **Timeframe mapping.** CCXT uses `1m/5m/15m/1h/4h/1d`, matching the app's existing
  `timeframe_seconds` keys — pass through.
- **Config:** `exchange` id (default `binance` for depth; document `coinbase`/`kraken` for
  exact USD), optional `quote_map`, optional API keys (not required for public OHLCV).

#### 2. `CsvImporter` (`data/csv_import.py`)

- Parse a CSV of OHLCV bars with a configurable column mapping (presets for
  cryptodatadownload and binance.vision layouts), normalize to the canonical row
  (`ts` = UTC epoch seconds, OHLCV floats), and `store.upsert_df(symbol, timeframe, df)`.
- Skips malformed rows, returns a count of imported vs skipped.

#### 3. `Backfiller` (`data/backfill.py`)

- Orchestrates: for each `(symbol, timeframe)` in config over `[start, now]`, pull via
  `CcxtProvider.get_candles_range` (or read a CSV via `CsvImporter`), upsert into `CandleStore`.
- **Idempotent / resumable:** before fetching a range, consult `CandleStore.coverage` and skip
  ranges already present, so a re-run only fills gaps and a crash mid-run is safe.
- Emits progress (bars written, per-symbol coverage start/end).

#### 4. `CandleStore.coverage` (`data/store.py`, small addition)

- `coverage(symbol, timeframe) -> {min_ts, max_ts, count}` — one query, powers resumability
  and the status endpoint. Only addition to existing store.

#### 5. Wiring

- **CLI:** `swingbot-backfill` entry in `pyproject.toml` scripts. Args:
  `--exchange`, `--symbols`, `--timeframes`, `--start`, `--csv <file> --symbol --timeframe`.
- **API (token-guarded, mirrors existing bg-job patterns in `web.py`):**
  - `POST /api/archive/backfill` — kick a backfill in a background thread (like the poller).
  - `GET /api/archive/status` — per-symbol/timeframe coverage (min/max ts, count) from
    `CandleStore.coverage`. (Powers a small UI later; not required for Phase 1.)
- **Config:** an `archive` section (exchange, `symbols`, `timeframes`, `history_start` /
  depth). Defaults: `exchange=binance`, the curated universe symbols, `[5m,15m,1h]`,
  ~2 years back (e.g. `history_start=2024-06-01`).

### Storage

Reuse `~/.swingbot/candles.db` `CandleStore` (`bars` keyed by symbol/timeframe/ts, WAL,
idempotent upsert). The live 60s poller and the archive share the store; upserts make this
safe. Sizing is trivial for SQLite (2y of 15m ≈ ~70k bars/symbol).

### Error handling

- CCXT rate limits → `enableRateLimit=True` + chunked pagination + bounded ret/backoff;
  a failed chunk is logged and the backfill continues.
- Bad CSV rows skipped with a count, never abort the import.
- Backfill idempotent/resumable; re-running fills only gaps.
- Backfill failures never touch the live trading loop (separate thread, separate concern).

### Testing (leanest, no network)

Mirror the existing style (network-gated tests are mocked/skipped, cf. the 4 skipped
Alpaca-network tests):

- `CcxtProvider`: symbol/timeframe mapping + range pagination against a **mocked** ccxt
  exchange (no network). Quote-map substitution.
- `CsvImporter`: parsing + normalization of both CSV layouts; malformed-row skipping.
- `Backfiller`: idempotency/resume against an in-memory `CandleStore` (re-run writes 0 new).
- `CandleStore.coverage`: min/max/count correctness.

No reference-parity check (per decision 3).

### Success criteria

- `swingbot-backfill --exchange binance --symbols BTC/USD --timeframes 15m --start 2024-06-01`
  populates `candles.db` with tens of thousands of BTC/USD 15m bars.
- `GET /api/archive/status` reports coverage `2024-06-01 → now` for BTC/USD 15m.
- Re-running the same backfill writes ~0 new bars (idempotent).
- A backtest of an existing preset over BTC/USD 15m now runs over the full multi-month
  window — `n_trades` and the date span are materially larger than today's ~11 trades / 5 days
  — with **no change to `backtest.py` / `strategy_search.py`**.
- Full test suite stays green (currently 207 passed / 4 skipped) plus the new unit tests.

### Out of scope for Phase 1

- Date-range *windowed* backtests ("2022 bear", "Covid panic" scenario picker) — Phase 2.
- A backfill/coverage UI panel — endpoint is enough for now.
- Scheduled automatic top-ups — the existing live poller already keeps the active timeframe
  warm; periodic deep top-up can come with Phase 2's background job.

---

## Phase 2 — Auto-Strategy Discovery *(outline only; its own spec later)*

Built on the Phase 1 archive. Sketch so context survives across sessions:

- **Sweep:** `presets.build_candidates` across the universe/watchlist × archetypes →
  `strategy_search`/`run_backtest` over the now-deep archive → rank by expectancy / profit
  factor. Bounded, cached (sweeps are heavy).
- **"Eligible now"** = historically-good **and** the strategy's confluence currently passes in
  a non-bearish regime (combine backtest rank with live signal state).
- **`GET /api/discovery`** + a cached background job that recomputes periodically.
- **UI — Discover panel:** ranked strategies per coin with btfdbot-style treatments to steal:
  named **scenario windows** (Covid panic / 2022 bear / recent) instead of raw date pickers;
  **metric buckets** (CAGR tiers, color-coded trades); **equity curve + Sharpe + max-drawdown +
  win-rate** summary; a **trade table**; **one-click arm** that calls the existing arm endpoint.
- **Depends on** Sub-project A's `/api/universe` + `/api/watchlist` for the coin list (until A
  lands, discovery can read a configurable universe list).

---

## Free data-source reference (for implementation)

- **CCXT** (`github.com/ccxt/ccxt`) — unified `fetch_ohlcv` across Binance/Coinbase/Kraken/…,
  public OHLCV needs no key. Primary provider.
- **Binance public dumps** (`data.binance.vision`) — bulk ZIP/CSV klines back to 2017, USDT
  quote. Deepest free history; feed via `CsvImporter`.
- **Coinbase Advanced Trade candles** / **Kraken OHLC** — true USD quote (matches Alpaca
  execution); shallower via API. Use via CCXT when USD-exact history matters.
- **cryptodatadownload.com** — gap-verified 1-minute CSVs, 5+ years, many exchanges. Bulk seed
  via `CsvImporter`.
