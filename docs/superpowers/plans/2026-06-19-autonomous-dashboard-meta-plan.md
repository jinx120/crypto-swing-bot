# Autonomous Trading Dashboard — Meta Plan (Planning Guide)

> **For Opus 4.8:** Use this as a guide to write the detailed implementation plan. This outlines the structure, dependencies, and decomposition. Flesh out each phase with actual code steps, file paths, and test cases.

**Goal:** Build a read-only web dashboard that shows backtest results (EMA vs Kronos), live trades, current position, candle charts, and journal feed. No configuration, no buttons—just visibility.

**Overall Strategy:**
1. Reuse existing `backtest.py` + `SimulatedBroker` to generate backtest results
2. Add 5 simple FastAPI endpoints to serve backtest + live data from SQLite
3. Add 1 React dashboard page with 6 sections (chart, position, trades, comparison, stats, journal)
4. Run backtest once on startup (cache results), then poll live data every 10s

---

## Phase 1: Backend Data Layer (Python)

### 1.1 Backtest Result Storage
- **Goal:** Run backtest offline (once at app start), cache results in memory or simple JSON
- **Files to touch/create:**
  - `src/swingbot/backtest.py` — already exists, no changes needed (reuse as-is)
  - `src/swingbot/backtest_runner.py` (NEW) — orchestrator that runs both EMA and Kronos backtests, returns results dict
  - `tests/test_backtest_runner.py` — verify EMA and Kronos results are cacheable
- **Key questions for Opus:**
  - Should backtest results be cached in memory or written to a file/DB?
  - Should backtest run on app startup (blocking) or async in background?
  - How much historical data? (spec says: compare on 6 months of data, but validate on 1 week of paper)

### 1.2 Live Data Queries
- **Goal:** Extract live data from core-engine's SQLite (state.db, journal.db, candles.db)
- **Files to touch/create:**
  - `src/swingbot/queries/` (NEW directory) — clean SQL read-only queries
    - `live_position.py` — get current position (or None if flat)
    - `recent_trades.py` — get last N closed trades from journal
    - `recent_events.py` — get last N decision events from journal
    - `candles_window.py` — get last N candles for charting
  - `tests/test_queries/` — test each query against fixture SQLite DBs
- **Key questions for Opus:**
  - What columns exist in core-engine's journal.db and state.db? (Read existing schema or infer from code)
  - How far back should "recent" be? (last 50 trades? last 24 hours?)
  - Should queries handle missing DB gracefully (e.g., if engine hasn't run yet)?

---

## Phase 2: Backend API Layer (FastAPI)

### 2.1 Add API Endpoints
- **Goal:** Expose backtest + live data as JSON endpoints
- **Files to touch/create:**
  - `src/swingbot/webmain.py` (MODIFY) — add 5 new routes
    - `GET /api/backtest/ema` → returns `{win_rate, sharpe, total_pnl, trades, equity_curve}`
    - `GET /api/backtest/kronos` → returns same structure
    - `GET /api/live/position` → returns `{entry_price, current_price, qty, pnl, pnl_pct, stop, tp} | null`
    - `GET /api/live/trades` → returns `[{entry_ts, exit_ts, entry_price, exit_price, qty, pnl, pnl_pct, duration}, ...]`
    - `GET /api/live/journal` → returns `[{ts, kind, symbol, reason}, ...]` (last 20)
    - `GET /api/live/candles` → returns `[{ts, open, high, low, close, volume}, ...]` (last 100)
  - `tests/test_webmain_dashboard_endpoints.py` (NEW) — test each endpoint returns correct JSON shape
- **Key questions for Opus:**
  - Where should backtest be triggered? App startup? On-demand route?
  - Should equity curves be included in backtest response (for plotting)?
  - What if no trades exist? Return `[]` or special sentinel?

### 2.2 Backtest Initialization
- **Goal:** Ensure backtest results are ready when app starts
- **Files to touch/create:**
  - `src/swingbot/webmain.py` (MODIFY) — add FastAPI `lifespan` event to run backtest at startup
  - Store results in a class-level cache (e.g., `BacktestCache`)
- **Key questions for Opus:**
  - How long does backtest take? (6 months of data, 2 signals = ?)
  - Should startup block waiting for it, or return stale results if not ready?
  - What if backtest fails? (e.g., data missing) Should app still start?

---

## Phase 3: Frontend Layer (React)

### 3.1 Create Dashboard Page
- **Goal:** Single-page dashboard with 6 panels
- **Files to touch/create:**
  - `frontend/src/pages/Dashboard.jsx` (NEW) — main layout with 6 sections
    - LayoutGrid or simple flexbox with 6 responsive panels
    - Each panel is its own component (see 3.2)
  - `frontend/src/api.js` (MODIFY if needed) — add helper functions to call new `/api/*` endpoints
  - `tests/Dashboard.test.jsx` (NEW if using React Testing Library)
- **Key questions for Opus:**
  - Should all 6 panels load in parallel or sequentially?
  - Polling interval? (spec says: every 10 seconds)
  - Should dashboard auto-refresh or have a manual refresh button?

### 3.2 Create Dashboard Panels (6 components)
Each panel should be modular:

1. **ChartPanel** (candles + EMAs + entry/exit markers)
   - Consumes: `candles.json`, `trades.json`
   - Library: `recharts` or `lightweight-charts`
   - Key: Plot candle OHLC + EMA(9) + EMA(20) + vertical lines for entries/exits

2. **CurrentPositionPanel** (entry price, P&L, stop/TP)
   - Consumes: `live_position.json` or `null`
   - Shows: "No position" if flat, or live trade details if open

3. **RecentTradesPanel** (last 10 trades: entry, exit, P&L)
   - Consumes: `recent_trades.json`
   - Shows: table with entry_ts, exit_ts, pnl, win/loss badge

4. **BacktestComparisonPanel** (EMA vs Kronos side-by-side)
   - Consumes: `backtest_ema.json`, `backtest_kronos.json`
   - Shows: win rate, Sharpe, total P&L (formatted as cards or simple table)

5. **LiveStatsPanel** (today's P&L, this week's win rate, consistency)
   - Consumes: `recent_trades.json`, `live_position.json`
   - Computes: sum P&L since today 00:00, win% over last 7 days

6. **JournalFeedPanel** (last 20 decision events)
   - Consumes: `journal.json` (last 20)
   - Shows: scrollable feed with timestamp, kind (decision/order/fill), reason

**Files to create:**
- `frontend/src/components/Dashboard/ChartPanel.jsx`
- `frontend/src/components/Dashboard/CurrentPositionPanel.jsx`
- `frontend/src/components/Dashboard/RecentTradesPanel.jsx`
- `frontend/src/components/Dashboard/BacktestComparisonPanel.jsx`
- `frontend/src/components/Dashboard/LiveStatsPanel.jsx`
- `frontend/src/components/Dashboard/JournalFeedPanel.jsx`
- `frontend/src/components/Dashboard/usePolling.js` — custom hook to poll endpoints every 10s

**Key questions for Opus:**
- Charting library: Use existing `recharts`? Or `lightweight-charts`?
- What if an endpoint is slow or times out? Show spinner or stale data?
- Should clicking a trade in RecentTradesPanel highlight it on the chart?

### 3.3 Integrate Dashboard into App Router
- **Goal:** Make dashboard accessible at a URL (e.g., `/dashboard`)
- **Files to touch/create:**
  - `frontend/src/App.jsx` (MODIFY) — add route to Dashboard page
  - Update nav bar if present
- **Key questions for Opus:**
  - Should dashboard be the default landing page, or secondary?

---

## Phase 4: Integration & Testing

### 4.1 End-to-End Test
- **Goal:** Verify full flow: backtest runs → endpoints serve data → dashboard renders
- **Files to touch/create:**
  - `tests/integration_dashboard_e2e.py` (NEW) — pytest that:
    1. Starts the FastAPI app
    2. Calls all 6 endpoints
    3. Verifies JSON shape
    4. Checks for stale/error states
- **Key questions for Opus:**
  - Use pytest fixtures for fake data or real backtest?
  - Should E2E include browser automation (Playwright) or just HTTP calls?

### 4.2 Manual Smoke Test
- **Goal:** Run the app locally and see dashboard
- **Steps (in plan):**
  - Start backend: `docker compose up -d`
  - Start frontend: `cd frontend && npm run dev`
  - Navigate to `http://localhost:5173/#/dashboard` (or configured URL)
  - Verify all 6 panels render (no blank/error states)
  - Verify data updates every 10s
  - Verify chart plots correctly

---

## Phase 5: Documentation & Deployment

### 5.1 API Documentation
- **Goal:** Document endpoints for future work
- **Files to touch/create:**
  - `docs/API_DASHBOARD.md` (NEW) — list all 6 endpoints, JSON schemas, example responses

### 5.2 Docker & Deployment
- **Goal:** Ensure dashboard runs in production Docker container
- **Files to touch/create:**
  - `docker-compose.yml` (VERIFY) — ensure frontend is served alongside backend
  - `Dockerfile` (MODIFY if needed) — may need to build frontend during image build
- **Key questions for Opus:**
  - Does Dockerfile already do multi-stage build for frontend? If not, add it.
  - Should backtest run on every container start, or be skipped in production?

---

## File Structure Summary

```
src/swingbot/
  backtest.py (existing—no changes)
  backtest_runner.py (NEW)
  queries/ (NEW dir)
    __init__.py
    live_position.py
    recent_trades.py
    recent_events.py
    candles_window.py
  webmain.py (MODIFY—add 5 endpoints + lifespan)

frontend/src/
  pages/
    Dashboard.jsx (NEW)
  components/Dashboard/ (NEW dir)
    ChartPanel.jsx
    CurrentPositionPanel.jsx
    RecentTradesPanel.jsx
    BacktestComparisonPanel.jsx
    LiveStatsPanel.jsx
    JournalFeedPanel.jsx
    usePolling.js
  api.js (MODIFY if needed—add helpers)
  App.jsx (MODIFY—add route)

tests/
  test_backtest_runner.py (NEW)
  test_queries/ (NEW dir)
    test_live_position.py
    test_recent_trades.py
    ...
  test_webmain_dashboard_endpoints.py (NEW)
  integration_dashboard_e2e.py (NEW)
```

---

## Decomposition & Task Sequencing

**Dependency order:**
1. Phase 1.1 (backtest runner) — no dependencies
2. Phase 1.2 (live queries) — depends on Phase 1.1 (backtest results exist)
3. Phase 2.1 (API endpoints) — depends on Phases 1.1 & 1.2
4. Phase 2.2 (backtest init) — depends on Phase 2.1
5. Phase 3.1–3.3 (frontend) — depends on Phase 2 (endpoints stable)
6. Phase 4 (testing) — depends on all above
7. Phase 5 (docs & deploy) — depends on Phase 4

**Each phase should produce:**
- Working, testable code
- Tests passing
- 1–2 commits per phase

---

## Success Criteria (for Opus)

- [ ] All 6 endpoints respond with correct JSON shape (no 500 errors)
- [ ] Dashboard renders all 6 panels without errors
- [ ] Live data updates every 10 seconds
- [ ] Backtest results are identical when run twice (deterministic)
- [ ] No network errors or timeouts (graceful degradation if slow)
- [ ] Charting library renders 100+ candles with EMA lines + markers
- [ ] Tests pass: `pytest -q` (all test files)
- [ ] Frontend builds: `npm run build` (no TypeScript/ESLint errors)
- [ ] Container builds and runs: `docker compose up -d` then dashboard accessible at `localhost:5173/#/dashboard` (or port configured)

---

## Notes for Opus

- **Reuse existing code:** `backtest.py`, `SimulatedBroker`, `TradeJournal`, `Metrics` — don't rewrite
- **Keep it simple:** No fancy animations, no real-time WebSocket, no animations—just polling
- **Read-only:** No buttons, no forms, no state mutations from frontend
- **Error handling:** If an endpoint fails, show "Loading..." or last known value, never crash
- **Charting:** Use `recharts` (lightweight, React-native) or `lightweight-charts` (pro-grade). Avoid D3 (overkill).
- **Testing:** TDD — write failing test first, then implementation. Use pytest + React Testing Library.
- **Commits:** One per task, clear messages. Example: "feat: add live position endpoint" / "feat: create chart panel"

**Questions to resolve before detailed planning:**
1. What's the actual schema of core-engine's `journal.db`? (Read from existing code or ask user)
2. How many candles to fetch for chart? (100? 500? Full history?)
3. Backtest on 6 months or 1 month for faster iteration?
4. Which charting library? (recharts vs lightweight-charts vs other)
5. Should dashboard auto-refresh or manual refresh button?
