# Graph Report - crypto-swing-bot  (2026-06-03)

## Corpus Check
- 158 files · ~99,138 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1681 nodes · 3330 edges · 95 communities (88 shown, 7 thin omitted)
- Extraction: 68% EXTRACTED · 32% INFERRED · 0% AMBIGUOUS · INFERRED: 1075 edges (avg confidence: 0.56)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `bb9dbe7d`
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
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]

## God Nodes (most connected - your core abstractions)
1. `StrategyProfile` - 97 edges
2. `MarketContext` - 89 edges
3. `StateStore` - 60 edges
4. `ProfileStore` - 57 edges
5. `TradeJournal` - 52 edges
6. `RiskManager` - 51 edges
7. `Orchestrator` - 50 edges
8. `PortfolioSupervisor` - 44 edges
9. `Regime` - 40 edges
10. `Trade` - 40 edges

## Surprising Connections (you probably didn't know these)
- `test_live_get_candles_smoke()` --calls--> `AlpacaData`  [INFERRED]
  tests/test_alpaca_data.py → src/swingbot/data/alpaca.py
- `test_candles_endpoint_serves_store()` --calls--> `create_app()`  [INFERRED]
  tests/test_candle_store.py → src/swingbot/web.py
- `test_candles_endpoint_without_store_returns_empty()` --calls--> `create_app()`  [INFERRED]
  tests/test_candle_store.py → src/swingbot/web.py
- `test_backfill_503_when_unconfigured()` --calls--> `create_app()`  [INFERRED]
  tests/test_web_archive.py → src/swingbot/web.py
- `test_backfill_requires_token()` --calls--> `create_app()`  [INFERRED]
  tests/test_web_archive.py → src/swingbot/web.py

## Import Cycles
- 1-file cycle: `src/swingbot/web.py -> src/swingbot/web.py`
- 1-file cycle: `src/swingbot/exits.py -> src/swingbot/exits.py`
- 1-file cycle: `src/swingbot/risk.py -> src/swingbot/risk.py`
- 1-file cycle: `src/swingbot/supervisor.py -> src/swingbot/supervisor.py`
- 1-file cycle: `src/swingbot/orchestrator.py -> src/swingbot/orchestrator.py`
- 1-file cycle: `src/swingbot/portfolio_risk.py -> src/swingbot/portfolio_risk.py`
- 1-file cycle: `src/swingbot/broker/simulated.py -> src/swingbot/broker/simulated.py`
- 1-file cycle: `src/swingbot/broker/base.py -> src/swingbot/broker/base.py`

## Communities (95 total, 7 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (22): bool, DataFrame, datetime, float, int, MarketData, ProfileStore, str (+14 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (32): KronosAdapter, Wraps a PredictorProtocol: column mapping, single-entry cache, timeout., Wraps a PredictorProtocol: column extraction, Series timestamps, cache, timeout., MarketContext, SignalResult, float, int, MarketContext (+24 more)

### Community 2 - "Community 2"
Cohesion: 0.16
Nodes (15): bars_to_df(), fetch_window_days(), parse_timeframe(), Days to fetch so `lookback` bars at `timeframe` are comfortably covered     (~3x, One batched bars request for many symbols. Returns {symbol: DataFrame}., DataFrame, float, int (+7 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (30): Broker, MarketDataProvider, Protocol, _load_kronos(), PredictorProtocol, Execute predictor.predict() in a thread; return None on timeout or error., Return forecast DataFrame, or None if inference fails/times out., Execute predictor.predict() in a thread; return None on timeout or error. (+22 more)

### Community 5 - "Community 5"
Cohesion: 0.07
Nodes (52): KronosForecastSignal, _df(), FakePredictor, _forecast_df(), _make_signal(), A new last candle timestamp causes a fresh predictor call., An exception inside predict() returns None without raising., Inference that exceeds timeout_s returns None without raising. (+44 more)

### Community 6 - "Community 6"
Cohesion: 0.11
Nodes (19): CcxtProvider, Market data via CCXT's unified API. Implements MarketDataProvider and     adds g, Fetch all bars in [start_ms, end_ms], paginating fetch_ohlcv forward.         CC, MarketDataProvider impl: most-recent `lookback` bars., DataFrame, float, int, str (+11 more)

### Community 7 - "Community 7"
Cohesion: 0.09
Nodes (22): AlpacaBroker, normalize_symbol(), Live/paper Alpaca crypto broker. Long-only, market orders (no brackets).      Ex, Tradable crypto */USD pairs, sorted. Network call — cache at call site., Alpaca crypto trading expects 'BTC/USD' form, uppercased., bool, float, str (+14 more)

### Community 8 - "Community 8"
Cohesion: 0.06
Nodes (26): DEFAULT_CFG, TIMEFRAMES, TOGGLES, ControlBar(), JournalTable(), MetricsPanel(), PositionPanel(), RiskPanel() (+18 more)

### Community 9 - "Community 9"
Cohesion: 0.07
Nodes (25): bool, float, int, Metrics, str, Trade, can_go_live(), Server-side gate: paper results must clear these bars before LIVE. (+17 more)

### Community 10 - "Community 10"
Cohesion: 0.07
Nodes (26): _bars(), _sup(), test_flatten_one_and_all(), test_halt_and_reset_portfolio_kill_switch(), test_journal_and_metrics_aggregate(), test_reload_is_noop_when_idle_and_unbuilt(), test_reload_picks_up_newly_armed(), test_set_mode_live_blocked_without_graduation() (+18 more)

### Community 11 - "Community 11"
Cohesion: 0.07
Nodes (47): datetime, ExitReason, float, bracket_levels(), exit_decision(), Return (stop_price, take_profit_price) for a long position., Decide whether a long position exits, and a reference exit price.      Priority:, test_live_spot_price_stop() (+39 more)

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
Cohesion: 0.16
Nodes (22): Backtest broker: models long-only bracket fills with fees + slippage.      Exit, SimulatedBroker, KronosForecastSignal, Kronos-based forecast signal. Satisfies the Signal protocol.      In tests, inje, DataFrame, float, int, Metrics (+14 more)

### Community 16 - "Community 16"
Cohesion: 0.12
Nodes (16): dependencies, lightweight-charts, marked, react, react-dom, devDependencies, vite, @vitejs/plugin-react (+8 more)

### Community 17 - "Community 17"
Cohesion: 0.16
Nodes (10): load_csv(), float, str, DataFrame, str, main(), run_from_files(), test_run_from_files_outputs_metrics() (+2 more)

### Community 18 - "Community 18"
Cohesion: 0.08
Nodes (35): Exception, bool, int, str, bool, DataFrame, int, str (+27 more)

### Community 19 - "Community 19"
Cohesion: 0.16
Nodes (16): CredentialStore, ProfileStore, float, Trade, Orchestrator, str, bool, CredentialStore (+8 more)

### Community 20 - "Community 20"
Cohesion: 0.17
Nodes (11): AlpacaData, Bar interval in seconds for a timeframe like '15m', '4h', '1d'., Force a live fetch from Alpaca and upsert into the store., Batched fetch for many symbols at one timeframe; upsert each into the store., Return up to `limit` bars (oldest-first). If the store is empty or the         n, Return up to `limit` bars (oldest-first). If the store is empty or the         n, timeframe_seconds(), bool (+3 more)

### Community 21 - "Community 21"
Cohesion: 0.13
Nodes (8): _bars(), _client(), _Ctl, FakeMarket, test_backtest_single_profile(), test_build_requires_token(), test_build_returns_ranked_results(), test_presets_lists_archetypes()

### Community 22 - "Community 22"
Cohesion: 0.12
Nodes (15): 1. Problem & Goal, 2. Decisions (from brainstorming), 3. Architecture, 4.1 `swingbot/presets.py` (new), 4.2 `swingbot/strategy_search.py` (new), 4.3 `web.py` endpoints, 4. Backend components, 5. Frontend (`Strategy.jsx` → 3 tiers) (+7 more)

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
Cohesion: 0.18
Nodes (10): Self-Review, Strategy Presets + Guided Builder Implementation Plan, Task 1: Preset archetypes + candidate builder, Task 2: Backtest search over candidates, Task 3: Web endpoints (presets / backtest / build), Task 4: Frontend API methods, Task 5: Preset gallery component, Task 6: Guided builder component (+2 more)

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
Cohesion: 0.27
Nodes (11): ConfluenceResult, Signal, Signal, OversoldSignal, RelativeStrengthSignal, VwapSignal, float, MarketContext (+3 more)

### Community 42 - "Community 42"
Cohesion: 0.12
Nodes (9): _df(), _FakeController, _FakeProfiles, test_candles_endpoint_serves_store(), test_candles_endpoint_without_store_returns_empty(), test_coverage_reports_min_max_count(), test_get_limit_returns_most_recent(), test_upsert_and_get_roundtrip() (+1 more)

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
Cohesion: 0.10
Nodes (19): 1. `CcxtProvider` (`data/ccxt_provider.py`), 2. `CsvImporter` (`data/csv_import.py`), 3. `Backfiller` (`data/backfill.py`), 4. `CandleStore.coverage` (`data/store.py`, small addition), 5. Wiring, Background & motivation, Components, Error handling (+11 more)

### Community 47 - "Community 47"
Cohesion: 0.13
Nodes (14): File Structure, Final verification, Important Alpaca Crypto Constraints (drive this whole phase), Phase 2 — Paper/Live Trading (Broker + Risk + State + Orchestrator) Implementation Plan, Task 1: Profile risk config + OpenPosition type, Task 2: Extract shared exit_decision; refactor SimulatedBroker, Task 3: Credential / .env loader, Task 4: SQLite StateStore (+6 more)

### Community 48 - "Community 48"
Cohesion: 0.13
Nodes (14): File Structure, Final verification, Phase 3A — Backend Control & Config API Implementation Plan, Security invariants (enforced in code, verified by tests where possible), Task 1: Dependencies + ProfileStore, Task 2: CredentialStore, Task 3: signal_snapshot (live display), Task 4: Graduation gate (+6 more)

### Community 49 - "Community 49"
Cohesion: 0.13
Nodes (14): File Map, Kronos Forecast Signal Implementation Plan, Phase 1 — Adapter, Signal, Tests, Registration, Phase 2 — Backtest Precompute Cache, Phase 3 — Dashboard Profile Fields, Phase 4 — Real-Model Smoke Test, Self-Review Checklist, Task 1: Add `[kronos]` optional dependency group (+6 more)

### Community 52 - "Community 52"
Cohesion: 0.18
Nodes (10): Clone & set up, Command-line tools, How it works (1-minute version), Production build (frontend), Project layout, Requirements, Run the dashboard (the normal way to use it), Security (+2 more)

### Community 53 - "Community 53"
Cohesion: 0.22
Nodes (8): File Structure, Phase 3B — React Valhalla Dashboard Implementation Plan, Task 1: Scaffold Vite app + Valhalla theme + API client, Task 2: Dashboard monitoring panels, Task 3: Control bar, Task 4: Strategy editor + Settings (credentials + token) + App shell, Task 5: End-to-end render verification + run docs, What Phase 3B delivers

### Community 54 - "Community 54"
Cohesion: 0.19
Nodes (13): CandleStore, AlpacaData, Alpaca crypto market data. Implements the MarketDataProvider protocol., One batched latest-trade request for many symbols. Returns {symbol: price}., MarketData, Serves candles from the CandleStore, fetching + caching from Alpaca on a     cac, Fetch + persist the active symbol's bars. Returns rows written., MarketData (+5 more)

### Community 55 - "Community 55"
Cohesion: 0.14
Nodes (12): datetime, float, int, PortfolioDecision, _dip(), FakeBroker, FakeData, _profile() (+4 more)

### Community 56 - "Community 56"
Cohesion: 0.23
Nodes (10): _client(), SWINGBOT_HOST env var overrides the default 127.0.0.1 bind address., SWINGBOT_HOST env var overrides the default 127.0.0.1 bind address., SWINGBOT_DATA_DIR env var overrides the default ~/.swingbot path., SWINGBOT_DATA_DIR env var overrides the default ~/.swingbot path., test_journal_and_metrics(), test_state_ok(), test_webmain_respects_swingbot_data_dir_env() (+2 more)

### Community 57 - "Community 57"
Cohesion: 0.06
Nodes (44): ArchiveConfig, ArgumentParser, BaseModel, ArchiveConfig, Backfiller, _default_symbols(), _default_timeframes(), _now_ms() (+36 more)

### Community 58 - "Community 58"
Cohesion: 0.20
Nodes (18): _warmup_bars(), _df(), _profile_with_kronos(), DataFrame, float, int, KronosAdapter, StrategyProfile (+10 more)

### Community 59 - "Community 59"
Cohesion: 0.13
Nodes (7): _client(), FakeController, test_get_profile_by_name(), test_invalid_profile_rejected(), test_profile_create_requires_token(), test_profile_crud_and_active(), test_profile_crud_and_arm()

### Community 60 - "Community 60"
Cohesion: 0.33
Nodes (5): Build, First-time setup (all in the browser), Run it, Security, SwingBot Dashboard (frontend)

### Community 61 - "Community 61"
Cohesion: 0.12
Nodes (8): bool, str, ProfileStore, SQLite-backed strategy profiles + an 'active' pointer., _client(), FakeController, test_universe_falls_back_without_creds(), test_watchlist_get_put_roundtrip_and_token()

### Community 63 - "Community 63"
Cohesion: 0.14
Nodes (9): CandlePoller, Periodically refreshes candles for all armed symbols via MarketData     (Alpaca, Periodically fetches OHLC bars for the active profile's symbol/timeframe     fro, str, _ensure_token(), main(), FakeMarket, FakeProfiles (+1 more)

### Community 64 - "Community 64"
Cohesion: 0.10
Nodes (19): 10. Testing, 11. Future directions (out of scope here), 1. Summary, 2. Goals / Non-Goals, 3. Constraints & Key Facts, 4.1 Approach (chosen: single supervisor loop), 4.2 `PortfolioSupervisor` (new — replaces single-strategy `BotService`), 4.3 `PortfolioRiskManager` (new — the heart of the rearchitecture) (+11 more)

### Community 65 - "Community 65"
Cohesion: 0.22
Nodes (9): str, create_app(), test_start_surfaces_error_as_400(), create_app() mounts StaticFiles at / when frontend/dist exists., create_app() mounts StaticFiles at / when frontend/dist exists., create_app() does NOT mount StaticFiles when frontend/dist is absent., create_app() does NOT mount StaticFiles when frontend/dist is absent., test_create_app_mounts_static_when_dist_exists() (+1 more)

### Community 66 - "Community 66"
Cohesion: 0.39
Nodes (4): _df(), _FakeProvider, test_get_fetches_on_empty_store(), test_get_serves_cache_when_fresh()

### Community 67 - "Community 67"
Cohesion: 0.20
Nodes (9): Connection, CandleStore, SQLite-backed OHLC candle store. One row per (symbol, timeframe, bar).      `ts`, Insert/replace bars from a DataFrame with columns         ts, open, high, low, c, Return up to `limit` most recent bars, oldest-first., Min/max bar timestamp (epoch seconds) and count for a series.         Powers bac, DataFrame, int (+1 more)

### Community 68 - "Community 68"
Cohesion: 0.15
Nodes (30): Position, Process one bar after entry. Returns a Trade if the position exited., Enum, RiskManager, datetime, ExitReason, float, Regime (+22 more)

### Community 69 - "Community 69"
Cohesion: 0.20
Nodes (19): FvgSignal, ICT bullish Fair Value Gap signal (long-only discount entry).      A bullish FVG, _df(), _fvg_df(), test_fvg_deeper_retrace_scores_higher(), test_fvg_min_gap_pct_filters_tiny_gaps(), test_fvg_name(), test_fvg_no_gap_returns_zero() (+11 more)

### Community 70 - "Community 70"
Cohesion: 0.22
Nodes (8): Phase 1 — Backend Concurrency Core Implementation Plan, Self-Review Notes (for the implementer), Task 1: PortfolioRiskManager (the single-writer portfolio gate), Task 2: Per-strategy keyed StateStore + portfolio state + migration, Task 3: ProfileStore armed set + live-eligible flag + portfolio settings, Task 4: Multi-symbol Alpaca data + MarketData.refresh_many, Task 5: Orchestrator portfolio-gate hooks, Task 6: PortfolioSupervisor + CachedProvider (the integrator)

### Community 71 - "Community 71"
Cohesion: 0.22
Nodes (8): Phase 3 — Frontend Multi-Chart Dashboard Implementation Plan, Self-Review Notes (for the implementer), Task 1: API client — portfolio + arming methods, Task 2: ChartPanel takes a required symbol; add mini mode, Task 3: PortfolioBanner + StrategyCard components, Task 4: Dashboard renders the portfolio grid, Task 5: Strategy page — arm/disarm + live-eligible + portfolio settings, Task 6: App wires the new state shape + portfolio banner

### Community 72 - "Community 72"
Cohesion: 0.36
Nodes (6): _p(), test_active_migrates_into_armed(), test_arm_disarm_and_list(), test_delete_disarms(), test_live_eligible_flag(), test_set_live_eligible_unarmed_raises()

### Community 73 - "Community 73"
Cohesion: 0.50
Nodes (6): build_signals(), _df(), _profile(), test_build_signals_returns_configured_signals(), test_confluence_fails_in_clean_uptrend(), test_confluence_passes_when_score_meets_threshold()

### Community 74 - "Community 74"
Cohesion: 0.14
Nodes (12): PortfolioRiskState, RiskState, OpenPosition, str, PortfolioRiskState, RiskState, SQLite persistence for the open position and risk state.      Single-row tables, Binds a StateStore to one strategy key, exposing the no-arg position/risk     in (+4 more)

### Community 75 - "Community 75"
Cohesion: 0.57
Nodes (7): _df(), _profile(), test_downtrend_when_price_below_falling_ma(), test_permits_entry_respects_allowed_regimes(), test_single_row_returns_neutral(), test_uptrend_when_price_above_rising_ma(), test_uses_htf_when_present()

### Community 76 - "Community 76"
Cohesion: 0.29
Nodes (6): 1. Where things stand, 2. The specific next task, 3. Files to focus on, 4. Run / test / deploy quick reference, 5. Known notes / gotchas, Handover — crypto-swing-bot

### Community 77 - "Community 77"
Cohesion: 0.29
Nodes (6): Phase 0 — Frontend Stabilization Implementation Plan, Self-Review Notes (for the implementer), Task 1: Tooltips render through a body portal, Task 2: ChartPanel survives empty / malformed / bad-symbol data, Task 3: API client distinguishes network failure from HTTP error, Task 4: App shows a backend-unreachable banner

### Community 78 - "Community 78"
Cohesion: 0.33
Nodes (5): Phase 2 — API Surface Implementation Plan, Self-Review Notes (for the implementer), Task 1: Supervisor control surface — journal, metrics, controls, reload, Task 2: Rework the FastAPI app for the portfolio surface, Task 3: Wire the supervisor into webmain + warm all armed symbols

### Community 79 - "Community 79"
Cohesion: 0.47
Nodes (3): _df(), _FakeMultiProvider, test_refresh_many_upserts_each_symbol()

### Community 80 - "Community 80"
Cohesion: 0.40
Nodes (4): Phase 4 — Live-Eligibility Gating Implementation Plan, Self-Review Notes (for the implementer), Task 1: Supervisor enforces live-eligibility per cycle, Task 2: End-to-end verification of the go-live flow

### Community 81 - "Community 81"
Cohesion: 0.60
Nodes (3): _pos(), test_positions_are_keyed_by_strategy(), test_strategy_state_view_binds_key()

### Community 82 - "Community 82"
Cohesion: 0.83
Nodes (3): _profile(), _series(), test_snapshot_shape()

### Community 83 - "Community 83"
Cohesion: 0.12
Nodes (16): Backend (additions to `web.py`), Current state (grounded in code), Dashboard grid, Decisions (locked with user), Devlog, Goal, Out of scope for A, Platform Improvement Roadmap — Design (+8 more)

### Community 84 - "Community 84"
Cohesion: 0.13
Nodes (14): Conventions (read once before starting), File Structure, Self-Review (completed during planning), Sub-project B Phase 1 — Historical Market-Data Archive Implementation Plan, Task 10: Manual end-to-end verification (success criteria), Task 1: `CandleStore.coverage`, Task 2: Add `ccxt` dependency, Task 3: `CcxtProvider` — symbol & timeframe mapping (+6 more)

### Community 85 - "Community 85"
Cohesion: 0.22
Nodes (7): _Ctl, _df(), _FakeBackfiller, _Profiles, test_backfill_503_when_unconfigured(), test_backfill_requires_token(), test_status_reports_coverage()

### Community 86 - "Community 86"
Cohesion: 0.15
Nodes (12): File Structure, Self-Review (author check — completed), Sub-project A — UI Cleanup + Multi-Position Dashboard — Implementation Plan, Task 1: Backend — fallback universe + ProfileStore watchlist & default_symbol  ✅ DONE (commit, 3 tests pass), Task 2: Backend — broker `list_usd_pairs()`  ✅ DONE (4 tests pass), Task 3: Backend — `/api/universe` + `/api/watchlist` endpoints  ✅ DONE (2 tests; fixed supervisor PortfolioSettings splat regression; corrected creds attr access), Task 4: Frontend — API client methods  ✅ DONE (build OK), Task 5: Frontend — symbol-agnostic Strategy page + Advanced disclosure  ✅ DONE (build OK; no TRX/USD literal remains) (+4 more)

### Community 87 - "Community 87"
Cohesion: 0.52
Nodes (6): _client(), test_control_actions_invoke_controller(), test_control_requires_token(), test_mode_switch_returns_gate_result(), test_start_requires_token(), test_start_stop_invoke_controller()

### Community 88 - "Community 88"
Cohesion: 0.28
Nodes (6): RegimeResult, bool, MarketContext, Regime, StrategyProfile, RegimeResult

### Community 89 - "Community 89"
Cohesion: 0.21
Nodes (6): datetime, OpenPosition, Broker is source of truth. If broker holds a position we don't have         reco, Broker is source of truth. If broker holds a position we don't have         reco, Force-close any open position at the latest price (manual control)., Force-close any open position at the latest price (manual control).

### Community 90 - "Community 90"
Cohesion: 0.22
Nodes (4): str, fallback_universe(), Curated fallback list of Alpaca-tradable crypto USD pairs.  Used when live broke, test_fallback_universe_is_usd_pairs()

### Community 91 - "Community 91"
Cohesion: 0.42
Nodes (8): _mgr(), test_allows_up_to_deployed_cap(), test_approves_when_clean(), test_blocks_on_max_concurrent(), test_blocks_when_deployed_cap_would_break(), test_blocks_when_kill_switch_active(), test_daily_loss_trips_kill_switch(), test_start_day_resets_counters()

### Community 93 - "Community 93"
Cohesion: 0.32
Nodes (6): float, position_size(), Fixed-fractional-risk sizing, clamped by a max position fraction.      stop_dist, test_position_cap_clamps_size(), test_risk_based_size(), test_zero_stop_distance_returns_zero()

### Community 94 - "Community 94"
Cohesion: 0.57
Nodes (7): _dip_and_recover(), _make_series(), _profile(), test_backtest_is_lookahead_safe_entry_at_next_open(), test_backtest_no_trades_in_pure_downtrend(), test_backtest_produces_trades_and_metrics(), test_backtest_rejects_too_short_input()

## Knowledge Gaps
- **342 isolated node(s):** `str`, `EntrySignal`, `float`, `float`, `int` (+337 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `StrategyProfile` connect `Community 19` to `Community 0`, `Community 1`, `Community 68`, `Community 5`, `Community 41`, `Community 74`, `Community 9`, `Community 11`, `Community 14`, `Community 15`, `Community 17`, `Community 18`, `Community 55`, `Community 88`, `Community 89`, `Community 58`, `Community 61`?**
  _High betweenness centrality (0.110) - this node is a cross-community bridge._
- **Why does `PortfolioSupervisor` connect `Community 0` to `Community 1`, `Community 68`, `Community 74`, `Community 10`, `Community 19`, `Community 54`, `Community 61`, `Community 63`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Why does `CandleStore` connect `Community 67` to `Community 66`, `Community 42`, `Community 10`, `Community 79`, `Community 20`, `Community 85`, `Community 54`, `Community 57`, `Community 63`?**
  _High betweenness centrality (0.076) - this node is a cross-community bridge._
- **Are the 95 inferred relationships involving `StrategyProfile` (e.g. with `ConfluenceResult` and `CredentialStore`) actually correct?**
  _`StrategyProfile` has 95 INFERRED edges - model-reasoned connections that need verification._
- **Are the 87 inferred relationships involving `MarketContext` (e.g. with `ConfluenceResult` and `CredentialStore`) actually correct?**
  _`MarketContext` has 87 INFERRED edges - model-reasoned connections that need verification._
- **Are the 45 inferred relationships involving `StateStore` (e.g. with `CredentialStore` and `ProfileStore`) actually correct?**
  _`StateStore` has 45 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `ProfileStore` (e.g. with `CandleStore` and `CredentialStore`) actually correct?**
  _`ProfileStore` has 35 INFERRED edges - model-reasoned connections that need verification._