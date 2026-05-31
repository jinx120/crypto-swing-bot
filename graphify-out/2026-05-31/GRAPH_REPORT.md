# Graph Report - crypto-swing-bot  (2026-05-31)

## Corpus Check
- 109 files · ~56,113 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1091 nodes · 2206 edges · 64 communities (59 shown, 5 thin omitted)
- Extraction: 65% EXTRACTED · 35% INFERRED · 0% AMBIGUOUS · INFERRED: 774 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6d24acf1`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 63|Community 63]]

## God Nodes (most connected - your core abstractions)
1. `MarketContext` - 77 edges
2. `StrategyProfile` - 74 edges
3. `Trade` - 40 edges
4. `TradeJournal` - 39 edges
5. `StateStore` - 39 edges
6. `Regime` - 38 edges
7. `RiskManager` - 38 edges
8. `ExitReason` - 37 edges
9. `ConfluenceEngine` - 37 edges
10. `Orchestrator` - 37 edges

## Surprising Connections (you probably didn't know these)
- `test_live_get_candles_smoke()` --calls--> `AlpacaData`  [INFERRED]
  tests/test_alpaca_data.py → src/swingbot/data/alpaca.py
- `test_candles_endpoint_serves_store()` --calls--> `create_app()`  [INFERRED]
  tests/test_candle_store.py → src/swingbot/web.py
- `test_candles_endpoint_without_store_returns_empty()` --calls--> `create_app()`  [INFERRED]
  tests/test_candle_store.py → src/swingbot/web.py
- `_client()` --calls--> `create_app()`  [INFERRED]
  tests/test_web_control.py → src/swingbot/web.py
- `test_start_surfaces_error_as_400()` --calls--> `create_app()`  [INFERRED]
  tests/test_web_control.py → src/swingbot/web.py

## Import Cycles
- 1-file cycle: `src/swingbot/web.py -> src/swingbot/web.py`
- 1-file cycle: `src/swingbot/exits.py -> src/swingbot/exits.py`
- 1-file cycle: `src/swingbot/risk.py -> src/swingbot/risk.py`
- 1-file cycle: `src/swingbot/orchestrator.py -> src/swingbot/orchestrator.py`
- 1-file cycle: `src/swingbot/broker/simulated.py -> src/swingbot/broker/simulated.py`
- 1-file cycle: `src/swingbot/broker/base.py -> src/swingbot/broker/base.py`

## Communities (64 total, 5 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.06
Nodes (85): Position, Backtest broker: models long-only bracket fills with fees + slippage.      Exit, Process one bar after entry. Returns a Trade if the position exited., SimulatedBroker, CredentialStore, Enum, ProfileStore, RegimeResult (+77 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (21): MarketContext, SignalResult, MarketContext, SignalResult, bool, float, int, KronosAdapter (+13 more)

### Community 2 - "Community 2"
Cohesion: 0.18
Nodes (13): bars_to_df(), fetch_window_days(), parse_timeframe(), Days to fetch so `lookback` bars at `timeframe` are comfortably covered     (~3x, DataFrame, int, str, test_bars_to_df_normalizes() (+5 more)

### Community 4 - "Community 4"
Cohesion: 0.19
Nodes (19): _maybe_precompute_kronos(), precompute_forecasts(), Run Kronos inference for every bar from warmup to end of df.      Returns a dict, If any signal is a KronosForecastSignal, pre-populate its adapter's cache., _warmup_bars(), _df(), _profile_with_kronos(), DataFrame (+11 more)

### Community 5 - "Community 5"
Cohesion: 0.06
Nodes (53): _df(), FakePredictor, _forecast_df(), _make_signal(), DataFrame, float, A new last candle timestamp causes a fresh predictor call., An exception inside predict() returns None without raising. (+45 more)

### Community 6 - "Community 6"
Cohesion: 0.17
Nodes (13): datetime, ExitReason, float, bracket_levels(), exit_decision(), Return (stop_price, take_profit_price) for a long position., Decide whether a long position exits, and a reference exit price.      Priority:, test_live_spot_price_stop() (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (21): AlpacaBroker, normalize_symbol(), Live/paper Alpaca crypto broker. Long-only, market orders (no brackets).      Ex, Alpaca crypto trading expects 'BTC/USD' form, uppercased., bool, float, str, str (+13 more)

### Community 8 - "Community 8"
Cohesion: 0.08
Nodes (24): DEFAULT_CFG, TIMEFRAMES, TOGGLES, ControlBar(), JournalTable(), MetricsPanel(), PositionPanel(), RiskPanel() (+16 more)

### Community 9 - "Community 9"
Cohesion: 0.15
Nodes (10): Broker, MarketDataProvider, Protocol, datetime, float, Regime, DataFrame, float (+2 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (25): bool, float, int, Metrics, str, Trade, can_go_live(), Server-side gate: paper results must clear these bars before LIVE. (+17 more)

### Community 11 - "Community 11"
Cohesion: 0.21
Nodes (14): _dip_and_recover(), FakeBroker, FakeData, _orch(), _profile(), _series(), test_killswitch_allows_exit_of_open_position(), test_reconcile_adopts_broker_position_if_state_empty() (+6 more)

### Community 12 - "Community 12"
Cohesion: 0.13
Nodes (23): AlpacaBroker Live/Paper Executor, ConfluenceEngine Signal Aggregator, FastAPI Web Backend Service, FvgSignal (Fair Value Gap), KronosAdapter Model Lifecycle Manager, KronosForecastSignal (Time-Series Foundation Model), Orchestrator Main Trading Loop, OversoldSignal (RSI-based) (+15 more)

### Community 13 - "Community 13"
Cohesion: 0.24
Nodes (17): Series, DataFrame, float, int, Series, atr(), lookback_return(), rolling_vwap() (+9 more)

### Community 14 - "Community 14"
Cohesion: 0.17
Nodes (8): _dip(), FakeBroker, FakeData, _orch(), _profile(), _series(), test_flatten_closes_open_position(), test_paused_blocks_new_entries()

### Community 15 - "Community 15"
Cohesion: 0.14
Nodes (6): _client(), FakeController, test_get_profile_by_name(), test_invalid_profile_rejected(), test_profile_create_requires_token(), test_profile_crud_and_active()

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (16): dependencies, lightweight-charts, marked, react, react-dom, devDependencies, vite, @vitejs/plugin-react (+8 more)

### Community 17 - "Community 17"
Cohesion: 0.09
Nodes (25): load_csv(), float, str, DataFrame, str, float, Replay candles through the real strategy. Lookahead-safe:     decide on the last, run_backtest() (+17 more)

### Community 18 - "Community 18"
Cohesion: 0.31
Nodes (13): _profile(), test_daily_counters_reset_on_new_day(), test_entry_allowed_after_cooldown_expires(), test_entry_approved_when_clean(), test_entry_blocked_during_cooldown(), test_entry_blocked_when_killswitch_active(), test_entry_blocked_when_max_concurrent_reached(), test_killswitch_trips_on_consecutive_losses() (+5 more)

### Community 19 - "Community 19"
Cohesion: 0.40
Nodes (4): Load the real Kronos model and verify predict() output shape.      Before runnin, ImportError message includes the pip install command., test_missing_kronos_import_gives_helpful_error(), test_real_predictor_returns_correct_shape()

### Community 20 - "Community 20"
Cohesion: 0.18
Nodes (10): AlpacaData, Connection, CandleStore, SQLite-backed OHLC candle store. One row per (symbol, timeframe, bar).      `ts`, Insert/replace bars from a DataFrame with columns         ts, open, high, low, c, Return up to `limit` most recent bars, oldest-first., bool, DataFrame (+2 more)

### Community 21 - "Community 21"
Cohesion: 0.57
Nodes (7): _df(), _profile(), test_downtrend_when_price_below_falling_ma(), test_permits_entry_respects_allowed_regimes(), test_single_row_returns_neutral(), test_uptrend_when_price_above_rising_ma(), test_uses_htf_when_present()

### Community 22 - "Community 22"
Cohesion: 0.23
Nodes (9): MarketData, Bar interval in seconds for a timeframe like '15m', '4h', '1d'., Serves candles from the CandleStore, fetching + caching from Alpaca on a     cac, Force a live fetch from Alpaca and upsert into the store., Return up to `limit` bars (oldest-first). If the store is empty or the         n, timeframe_seconds(), int, str (+1 more)

### Community 23 - "Community 23"
Cohesion: 0.33
Nodes (6): Crypto Swing-Trading Bot Design Spec, Kronos Forecast Signal Integration Design, Kronos Forecast Signal Implementation Plan, Phase 1 Strategy Engine + Backtest Implementation Plan, Phase 2 Paper/Live Trading Implementation Plan, Phase 3A Backend Control & Config API Implementation Plan

### Community 24 - "Community 24"
Cohesion: 0.47
Nodes (3): _p(), test_active_pointer(), test_save_get_list_delete()

### Community 25 - "Community 25"
Cohesion: 0.47
Nodes (3): _pos(), test_persistence_across_instances(), test_position_save_load_clear()

### Community 27 - "Community 27"
Cohesion: 0.83
Nodes (3): _profile(), _series(), test_snapshot_shape()

### Community 38 - "Community 38"
Cohesion: 0.05
Nodes (36): 10. Future Seams (designed for, not built in v1), 11.1 Stack, 11.2 Layout, 11.3 Control surface (full) + mandatory guardrails, 11.4 API sketch, 11.5 Config & credential management, 11. Front End — Monitoring Dashboard & Control API, 12. Tech Notes (non-binding, for the planner) (+28 more)

### Community 39 - "Community 39"
Cohesion: 0.07
Nodes (27): Architecture Overview, Backtest Lookahead Safety (Phase 2), Cache, Column Mapping, Component: `KronosAdapter` (`kronos_adapter.py`), Component: `KronosForecastSignal` (`kronos_forecast.py`), Confluence Registration, Constraints (+19 more)

### Community 40 - "Community 40"
Cohesion: 0.08
Nodes (25): 1. nvidia-container-toolkit, 2. Kronos model pre-download, Backend Changes, Data and credentials, docker-compose.yml, Docker GPU Deployment — Design Spec, Dockerfile (multi-stage), .dockerignore (+17 more)

### Community 41 - "Community 41"
Cohesion: 0.11
Nodes (28): ConfluenceResult, Signal, Signal, FvgSignal, Fair Value Gap signal. Interface only in Phase 1; returns neutral 0.      Implem, OversoldSignal, RelativeStrengthSignal, VwapSignal (+20 more)

### Community 42 - "Community 42"
Cohesion: 0.13
Nodes (8): _df(), _FakeController, _FakeProfiles, test_candles_endpoint_serves_store(), test_candles_endpoint_without_store_returns_empty(), test_get_limit_returns_most_recent(), test_upsert_and_get_roundtrip(), test_upsert_is_idempotent()

### Community 43 - "Community 43"
Cohesion: 0.10
Nodes (19): File Structure, Final verification, Phase 1 — Strategy Engine + Backtest Mode Implementation Plan, Task 0: Project scaffolding, Task 10: Metrics, Task 11: Broker protocol + SimulatedBroker, Task 12: Market data provider (interface + CSV historical), Task 13: Backtester orchestrator + end-to-end integration test (+11 more)

### Community 44 - "Community 44"
Cohesion: 0.11
Nodes (18): A. Simple starter (no GPU needed), B. Kronos-assisted (uses the GPU), Controls reference, Core, Entry signals (enable at least one), Example profiles (JSON), Exits (always active), Going live (+10 more)

### Community 45 - "Community 45"
Cohesion: 0.12
Nodes (16): Docker GPU Deployment Implementation Plan, File Map, Self-Review, Task 10: Push all commits, Task 11: Pre-download Kronos model weights, Task 12: Build the Docker image, Task 13: Start the container and verify web UI, Task 1: Install nvidia-container-toolkit on host (+8 more)

### Community 46 - "Community 46"
Cohesion: 0.16
Nodes (12): PredictorProtocol, Execute predictor.predict() in a thread; return None on timeout or error., Return forecast DataFrame, or None if inference fails/times out., Execute predictor.predict() in a thread; return None on timeout or error., Matches the real KronosPredictor.predict() signature., Return forecast DataFrame, or None if inference fails/times out., bool, DataFrame (+4 more)

### Community 47 - "Community 47"
Cohesion: 0.13
Nodes (14): File Structure, Final verification, Important Alpaca Crypto Constraints (drive this whole phase), Phase 2 — Paper/Live Trading (Broker + Risk + State + Orchestrator) Implementation Plan, Task 1: Profile risk config + OpenPosition type, Task 2: Extract shared exit_decision; refactor SimulatedBroker, Task 3: Credential / .env loader, Task 4: SQLite StateStore (+6 more)

### Community 48 - "Community 48"
Cohesion: 0.13
Nodes (14): File Structure, Final verification, Phase 3A — Backend Control & Config API Implementation Plan, Security invariants (enforced in code, verified by tests where possible), Task 1: Dependencies + ProfileStore, Task 2: CredentialStore, Task 3: signal_snapshot (live display), Task 4: Graduation gate (+6 more)

### Community 49 - "Community 49"
Cohesion: 0.13
Nodes (14): File Map, Kronos Forecast Signal Implementation Plan, Phase 1 — Adapter, Signal, Tests, Registration, Phase 2 — Backtest Precompute Cache, Phase 3 — Dashboard Profile Fields, Phase 4 — Real-Model Smoke Test, Self-Review Checklist, Task 1: Add `[kronos]` optional dependency group (+6 more)

### Community 50 - "Community 50"
Cohesion: 0.12
Nodes (17): KronosForecastSignal, KronosAdapter, _load_kronos(), Populate the precomputed forecast cache (used by run_backtest)., Lazy import gate — only called from KronosAdapter.from_profile().      Kronos is, Wraps a PredictorProtocol: column mapping, single-entry cache, timeout., Wraps a PredictorProtocol: column extraction, Series timestamps, cache, timeout., Load real Kronos model. Only call this when torch is installed.          Verify (+9 more)

### Community 52 - "Community 52"
Cohesion: 0.18
Nodes (10): Clone & set up, Command-line tools, How it works (1-minute version), Production build (frontend), Project layout, Requirements, Run the dashboard (the normal way to use it), Security (+2 more)

### Community 53 - "Community 53"
Cohesion: 0.22
Nodes (8): File Structure, Phase 3B — React Valhalla Dashboard Implementation Plan, Task 1: Scaffold Vite app + Valhalla theme + API client, Task 2: Dashboard monitoring panels, Task 3: Control bar, Task 4: Strategy editor + Settings (credentials + token) + App shell, Task 5: End-to-end render verification + run docs, What Phase 3B delivers

### Community 54 - "Community 54"
Cohesion: 0.23
Nodes (9): CandleStore, AlpacaData, Alpaca crypto market data. Implements the MarketDataProvider protocol., Fetch + persist the active symbol's bars. Returns rows written., MarketData, float, CredentialStore, int (+1 more)

### Community 55 - "Community 55"
Cohesion: 0.31
Nodes (8): _client(), SWINGBOT_HOST env var overrides the default 127.0.0.1 bind address., SWINGBOT_DATA_DIR env var overrides the default ~/.swingbot path., test_journal_and_metrics(), test_state_ok(), test_webmain_respects_swingbot_data_dir_env(), test_webmain_respects_swingbot_host_env(), test_write_requires_token()

### Community 56 - "Community 56"
Cohesion: 0.25
Nodes (8): FastAPI, str, create_app(), test_start_surfaces_error_as_400(), create_app() mounts StaticFiles at / when frontend/dist exists., create_app() does NOT mount StaticFiles when frontend/dist is absent., test_create_app_mounts_static_when_dist_exists(), test_create_app_skips_static_when_dist_missing()

### Community 57 - "Community 57"
Cohesion: 0.30
Nodes (3): str, ProfileStore, SQLite-backed strategy profiles + an 'active' pointer.

### Community 58 - "Community 58"
Cohesion: 0.52
Nodes (6): _client(), test_control_actions_invoke_controller(), test_control_requires_token(), test_mode_switch_returns_gate_result(), test_start_requires_token(), test_start_stop_invoke_controller()

### Community 59 - "Community 59"
Cohesion: 0.53
Nodes (5): BaseModel, ActiveBody, CredBody, ModeBody, ProfileBody

### Community 60 - "Community 60"
Cohesion: 0.33
Nodes (5): Build, First-time setup (all in the browser), Run it, Security, SwingBot Dashboard (frontend)

### Community 61 - "Community 61"
Cohesion: 0.24
Nodes (6): CandlePoller, Periodically refreshes the active profile's symbol/timeframe candles via     Mar, Periodically fetches OHLC bars for the active profile's symbol/timeframe     fro, str, _ensure_token(), main()

### Community 63 - "Community 63"
Cohesion: 0.39
Nodes (4): _df(), _FakeProvider, test_get_fetches_on_empty_store(), test_get_serves_cache_when_fresh()

## Knowledge Gaps
- **217 isolated node(s):** `str`, `str`, `EntrySignal`, `float`, `float` (+212 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `StrategyProfile` connect `Community 0` to `Community 4`, `Community 5`, `Community 41`, `Community 10`, `Community 11`, `Community 14`, `Community 17`, `Community 50`, `Community 57`?**
  _High betweenness centrality (0.126) - this node is a cross-community bridge._
- **Why does `MarketContext` connect `Community 0` to `Community 1`, `Community 5`, `Community 41`, `Community 10`, `Community 50`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Why does `BotService` connect `Community 10` to `Community 0`, `Community 7`, `Community 54`, `Community 57`, `Community 61`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 75 inferred relationships involving `MarketContext` (e.g. with `ConfluenceResult` and `CredentialStore`) actually correct?**
  _`MarketContext` has 75 INFERRED edges - model-reasoned connections that need verification._
- **Are the 72 inferred relationships involving `StrategyProfile` (e.g. with `ConfluenceResult` and `CredentialStore`) actually correct?**
  _`StrategyProfile` has 72 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `Trade` (e.g. with `Position` and `SimulatedBroker`) actually correct?**
  _`Trade` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `TradeJournal` (e.g. with `CredentialStore` and `ProfileStore`) actually correct?**
  _`TradeJournal` has 36 INFERRED edges - model-reasoned connections that need verification._