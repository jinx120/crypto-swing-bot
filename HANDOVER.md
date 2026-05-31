# Handover — crypto-swing-bot

_Last updated: 2026-05-31. Branch `master` @ `7218094`, pushed to `origin/master`._

## 1. Where things stand

Personal long-only Alpaca crypto swing bot (target TRX/USD). Phases 1–3 (strategy engine, paper/live trading, web dashboard) were already complete. This session added three feature lines, all **committed and pushed to `master`** and **deployed** in Docker (`crypto-swing-bot-swingbot-1`, http://localhost:8000):

1. **Glassmorphism UI reskin** — `frontend/src/theme.css` rewritten (Inter, frosted `backdrop-filter` panels, indigo/purple accents, ambient background, reduced-motion safe). Class names unchanged, so components were untouched.

2. **Alpaca→SQLite market-data pipeline + dashboard chart**
   - `src/swingbot/data/store.py` `CandleStore` (SQLite `bars(symbol,timeframe,ts,o,h,l,c,v)`, WAL, upsert + range query; `ts`=UTC epoch secs).
   - `src/swingbot/data/market.py` `MarketData` — read-through cache; fetches+caches ANY timeframe on demand from Alpaca (`max_age`=bar interval). `timeframe_seconds()` helper.
   - `src/swingbot/data/poller.py` `CandlePoller` — 60s background thread, keeps the active profile's timeframe warm, independent of the trading loop.
   - `GET /api/candles` in `web.py`; wired in `webmain.py` (`~/.swingbot/candles.db`).
   - `frontend/src/components/ChartPanel.jsx` — TradingView **Lightweight Charts v5**: candlesticks + volume, ▲/▼ trade markers from the journal, **timeframe switcher** (1m–1d), **stop/target/entry price lines** from `state.position`, and an **extensible localStorage toggle/config** (gear popover: volume, markers, lines, SMA/EMA w/ periods, grid, magnet crosshair, log scale). Add an overlay = one row in its `TOGGLES` array.

3. **Strategy presets + backtest-driven guided builder** (this session's main feature)
   - `src/swingbot/presets.py` — 4 archetypes (Conservative / Balanced / Aggressive / AI-Kronos) + `RISK`/`STYLE` param maps + `build_candidates(symbol, risk, style, ai)`.
   - `src/swingbot/strategy_search.py` — `backtest_profile()` runs the **existing** `run_backtest` over `MarketData` candles; `search()` ranks candidates by expectancy→win_rate→n_trades, captures per-candidate failures without aborting; `metrics_dict()` serializes defensively.
   - `web.py` endpoints: `GET /api/presets`, `POST /api/strategy/backtest`, `POST /api/strategy/build` (token-guarded; `400` when no creds).
   - `frontend/src/components/PresetGallery.jsx` + `StrategyBuilder.jsx` → 3-tier Strategy page; both prefill the **existing detailed form** via `applyProfile`/`parseProfile`. Nothing removed.

**Tests:** full suite **160 passed / 4 skipped** (`.venv/bin/python -m pytest -q`). New: `tests/test_candle_store.py`, `tests/test_market.py`, `tests/test_presets.py`, `tests/test_strategy_search.py`, `tests/test_web_strategy.py`.

**Design docs:** `docs/superpowers/specs/2026-05-31-strategy-presets-builder-design.md` (spec, incl. §9 future directions), `docs/superpowers/plans/2026-05-31-strategy-presets-builder.md` (implementation plan).

## 2. The specific next task

**Validate the strategy builder end-to-end with real market data, then start the historical data archive.**

The build/backtest/chart features are code-complete but currently show empty/"set Alpaca credentials" because **no Alpaca credentials are set** in the deployed container (`/api/credentials` → null, `/api/profiles/active` → null). Concretely, next session should:

1. **Set credentials** in the UI **Settings** tab (Alpaca key id + secret; the `.env` historically had key `PKZDRW…` but the secret must be entered by the user). Then set an **active strategy** (Strategy tab → Use a preset → Save → Set active).
2. **Verify the chart** populates within ~60s (candles, and markers/lines once trades exist) and the **timeframe switcher** fetches other TFs on demand.
3. **Verify the guided builder**: Strategy tab → Guided builder → pick TRX/USD + Balanced + Swing → **Build & backtest** → confirm a **ranked candidate table with non-empty metrics** and a ★ recommended row; "Use this" loads it into the form.
4. Then begin the next milestone — **spec §9.2 persistent historical market-data archive** (a `Backfiller` beside `CandlePoller`, a `source` column on `bars`, deep backfill paging), which is the substrate for **§9.1 the extensive backtesting platform** (equity curves, parameter sweeps, walk-forward, saved runs, async jobs — à la btfdbot.com/backtester). `CandleStore`/`MarketData`/`strategy_search` are the kernels; `MarketDataProvider` protocol (`src/swingbot/data/base.py`) is the seam for adding free providers (Binance/Kraken/CryptoCompare/Polygon…).

## 3. Files to focus on

| Area | Files |
|------|-------|
| Market data / archive (next milestone) | `src/swingbot/data/store.py`, `market.py`, `poller.py`, `base.py` (provider protocol) |
| Strategy generation | `src/swingbot/presets.py`, `src/swingbot/strategy_search.py`, `src/swingbot/backtest.py` (`run_backtest`) |
| API surface | `src/swingbot/web.py`, `src/swingbot/webmain.py` |
| Chart UI | `frontend/src/components/ChartPanel.jsx` |
| Strategy UI | `frontend/src/pages/Strategy.jsx`, `components/PresetGallery.jsx`, `components/StrategyBuilder.jsx` |
| Design intent | `docs/superpowers/specs/2026-05-31-strategy-presets-builder-design.md` (§9 = roadmap) |

## 4. Run / test / deploy quick reference

```bash
# tests
.venv/bin/python -m pytest -q                      # 160 passed / 4 skipped

# frontend build
cd frontend && npm run build

# rebuild + redeploy container (PyTorch/Kronos base; ~minutes)
docker compose build swingbot && docker compose up -d swingbot
#   app: http://localhost:8000   (token printed in `docker compose logs swingbot`)

# knowledge graph (after code changes)
graphify update .
```

## 5. Known notes / gotchas

- **FVG signal is a stub** (`signals/fvg.py`) — always scores 0; archetypes don't use it.
- **AI/Kronos** candidates are slow (torch model load) — builder caps to 2–3 candidates when AI is on; needs the `[kronos]` extra (already in the Docker image, cloned to `/kronos`, `PYTHONPATH=/kronos`).
- **Full-page Playwright screenshots** show white below the fold = `backdrop-filter`+fixed-bg artifact, NOT a bug; use a tall viewport to verify.
- Backtests/builds run on **recent cached candles** (lookback cap), not deep history yet — that's the §9.2 archive work.
- Data dir is `~/.swingbot/` (host) → `/data` (container): `candles.db`, `swingbot.db` (profiles+state), `credentials.json`, `token`.
