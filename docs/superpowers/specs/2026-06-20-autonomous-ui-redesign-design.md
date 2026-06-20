# Autonomous-First UI Redesign — Design Spec

**Date:** 2026-06-20
**Status:** Approved (brainstorm) — ready for implementation plan
**Scope:** Frontend only (`crypto-swing-bot/frontend/`). No backend behavior change.
**Branch:** `core-engine`

---

## 1. Context & motivation

The trading engine has converged on an **autonomous loop** (Visible Autonomous Entry Phases 1–6,
Portfolio Rebalancing, Broker Connection Manager). The frontend, however, is still **manual-trading
first**: the default landing page is the old manual `Dashboard` (portfolio banner + chart + a
Start/Stop `ControlBar`) from the Sub-project-A era, and the genuinely recent work is scattered — the
Autonomous dashboard is a secondary tab, and the Rebalance + Broker-connection panels are buried inside
Settings. Several tabs (`Strategy`, `Discover`, `Brain`, `Health`, `Guide`) are leftover surfaces from
earlier sub-projects.

The user's intent: **completely restructure the UI around the autonomous loop as the centerpiece**, cut
the manual-era remnant surfaces, and apply a cohesive modern visual system.

## 2. Goals

- **Autonomous loop is the home.** The first thing a user sees is what the bot is doing right now.
- **Multi-coin by design.** The bot trades multiple symbols (`btc_trend`, `eth_trend` today,
  watchlist-extensible). The home scales to N coins via a per-coin grid.
- **Manage what is traded.** Add/remove coins (watchlist) and arm/disarm strategies directly from the UI.
- **Manual Start/Stop** of the loop, folded into the home — not a separate manual dashboard.
- **One place for plumbing.** Broker connection, rebalance config, and advanced controls consolidated in
  Settings. The broker-connection panel is the documented recovery path for the current Alpaca 401.
- **Cohesive visual system** (Tailwind + shadcn/ui) replacing the hand-rolled `theme.css`.

## 3. Non-goals (explicit scope boundaries)

- **No backend changes.** Brain, Discovery, and Usage-Agent endpoints and the nightly self-test cron
  keep running headless. This redo removes their *UI surfaces only*. The 659-passing backend test suite
  is expected to stay green and untouched. Physically removing those backend subsystems is a separate,
  riskier project and is **out of scope**.
- **No new trading logic, strategies, or signals.**
- **No deep-history / Sharpe backtesting work.** (Feasible for crypto via the existing Coinbase-backed
  B1 archive, but a separate future project.)
- **No paper→live promotion flow rework** beyond surfacing the existing controls.

## 4. Information architecture

From 8 tabs to **2 routes + 1 detail view**, on the existing **HashRouter** so FastAPI keeps serving
the static bundle with no server-side routing change.

| Route | Name | Purpose |
|---|---|---|
| `#/` | **Mission Control** | The autonomous loop — centerpiece / home |
| `#/coin/:symbol` | **Coin Detail** | Per-coin deep-dive (reuses the 6 AutoDash panels) |
| `#/settings` | **Settings** | Broker connection, rebalance config, advanced controls |

`react-router-dom` with `HashRouter` (3 routes). The token bootstrap (`ensureToken()` →
`/api/auth/bootstrap`) and the existing `TokenGate` fallback are preserved.

## 5. Mission Control (`#/`)

```
┌ ● RUNNING   PAPER   equity $10,240   today ▲ +2.1%        [ Stop ] ┐
│   broker: connected ✓   ·   backend ✓   ·   reliability 98%        │
├───────────────────────────────────────────────────────────────────┤
│  COINS                                              [ + Add coin ]  │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                      │
│  │ BTC  ●long │ │ ETH  ●flat │ │ SOL ○armed │   ← one card / coin   │
│  │ +$120 1.2% │ │   —        │ │   —        │     sparkline + last  │
│  │ ENTER:xover│ │ HOLD       │ │ —          │     decision + arm/   │
│  │ [flatten]  │ │ [disarm]   │ │ [disarm]   │     disarm / flatten  │
│  └────────────┘ └────────────┘ └────────────┘                      │
├───────────────────────────────────────────────────────────────────┤
│  REBALANCE  soft · on target · drift 1.2%        [configure →]      │
├───────────────────────────────────────────────────────────────────┤
│  DECISION JOURNAL (live)                                            │
│  10:42  BTC  ENTER  ema fast crossed slow, regime=trending          │
│  10:42  ETH  HOLD   no signal                                       │
└───────────────────────────────────────────────────────────────────┘
```

### 5.1 Status strip (replaces `nav` + `PortfolioBanner` + `ControlBar` + `LifecycleBanner` + mode hint)

- **Loop state**: RUNNING / PAUSED / STOPPED indicator from `GET /api/health/trading` +
  `running_desired` / `running_actual` from lifecycle.
- **Mode badge**: PAPER / LIVE from `state.portfolio.mode`.
- **Equity + today's P&L**: from `/api/state`.
- **Health dots**: backend reachable, broker authorized, reliability ratio.
- **Primary Start/Stop toggle**: `POST /api/control/start | stop`. Single toggle that renders "Stop"
  while running (matches the s6-guide affordance contract).
- **Broker-unauthorized banner**: when the broker returns unauthorized (today's 401 on the stale paper
  key), an amber banner: *"Broker not connected — fix in Settings"* deep-linking to `#/settings`. This
  is the exact recovery path the Broker Connection Manager was built for.

### 5.2 Coins grid (centerpiece)

One card per traded symbol. Data from `GET /api/state` (per-strategy `kind` / `label` / position /
`unrealized` / `mark_price` / `mark_ts` / `probe_complete`) and per-strategy last decision.

- **Card contents**: symbol, status (long / short / flat / armed / disarmed), position size + entry,
  unrealized P&L, mark price, last decision code + reason, optional mini sparkline (lightweight-charts
  mini mode already supported).
- **Card actions**: arm / disarm (`POST /api/strategies/arm | disarm`), flatten
  (`POST /api/control/{name}/flatten`).
- **[+ Add coin]**: dialog listing `GET /api/universe` minus current `GET /api/watchlist`; selecting a
  coin writes `PUT /api/watchlist` and arms its managed strategy.
- **Click a card** → `#/coin/:symbol`.

### 5.3 Rebalance strip

Compact read of `GET /api/rebalance/status` + `GET /api/rebalance/settings`: enabled?, mode (soft/hard),
drift, on-target indicator. "configure →" jumps to Settings. When disabled, a quiet "Rebalancing off"
with the same link.

### 5.4 Live decision journal

Streaming feed of the bot's reasoning — the autonomy made visible. Sourced from `/api/state` per-strategy
decisions and `/api/health/trading` decision window (and/or `/api/live/journal`). Includes a small
reliability summary (cycle-completion ratio).

## 6. Coin Detail (`#/coin/:symbol`)

Full-screen drill-down that **reuses the existing AutoDash panels**, restyled:

| Panel | Source (per-symbol) |
|---|---|
| Chart (entry/exit markers) | `GET /api/candles?symbol=…` |
| Current Position | `GET /api/state` (this strategy/symbol) |
| Live Stats | `GET /api/state` / `GET /api/metrics?strategy=…` |
| EMA-vs-Kronos backtest | `GET /api/backtest/ema | kronos` — **single-symbol, see §10** |
| Recent Trades | `GET /api/journal?strategy=…` |
| Decision Journal | `GET /api/journal?strategy=…` / `/api/live/journal` |

Per-coin controls: arm / disarm, flatten, remove from watchlist (`PUT /api/watchlist` minus this symbol).

## 7. Settings (`#/settings`)

Consolidates the keeper surfaces into one screen:

1. **Broker connection** (top): the schema-driven Broker Connection Manager panel — `GET /api/brokers`,
   `PUT /api/brokers/{id}/credentials`, `POST /api/brokers/{id}/test`, `POST /api/brokers/active`,
   `POST /api/brokers/reconnect`. Test → Save → Reconnect, secrets masked. This is the 401 fix path.
2. **Rebalance configuration**: today's `RebalancePanel` — `GET/POST /api/rebalance/settings`,
   `/api/rebalance/targets`, `POST /api/rebalance/run`.
3. **Advanced controls**: pause / resume / halt (`/api/control/*`), live-eligibility graduation
   (`POST /api/strategies/live-eligible`), portfolio settings (`GET/PUT /api/portfolio/settings`),
   token gate (`TokenGate`) for non-localhost deployments.

## 8. Removed UI inventory (the remnants)

**Deleted pages:** `pages/Dashboard.jsx`, `pages/Strategy.jsx`, `pages/Discover.jsx`, `pages/Brain.jsx`,
`pages/Health.jsx`, `pages/Guide.jsx`.

**Deleted components (orphaned once the pages above are gone):** `StrategyBuilder`, `StrategyManager`,
`StrategyCard`, `PresetGallery`, `SignalPanel`, `RiskPanel`, the old top-level `ChartPanel.jsx` (manual,
240 lines), `JournalTable`, `MetricsPanel`, `StatusBanner`, `PositionGrid`, `PositionPanel`,
`PortfolioBanner`, `ControlBar`, `Hint`, `PendingOrders`.

**Kept & restyled:** `components/AutoDash/*` (ChartPanel, CurrentPositionPanel, LiveStatsPanel,
RecentTradesPanel, BacktestComparisonPanel, JournalFeedPanel, `usePolling.js`), `RebalancePanel`,
`TokenGate`, `api.js`, `main.jsx`.

**`api.js`:** keep all methods (harmless) initially; optionally trim the now-unused discovery / brain /
agent / manual-strategy-build / presets methods in a dedicated cleanup task. Trimming is a nicety, not a
requirement.

## 9. Tech stack & dependencies

- **Kept:** React 18, Vite, `lightweight-charts` v5, `api.js`, token bootstrap, `usePolling` hook.
- **Added:** `tailwindcss` + `postcss` + `autoprefixer`; **shadcn/ui** (Radix primitives,
  `class-variance-authority`, `tailwind-merge`, `clsx`, `lucide-react` icons); `react-router-dom`
  (HashRouter).
- **Removed:** `marked` (only the cut Guide page used it); the hand-rolled `theme.css` (replaced by the
  Tailwind/shadcn system).
- **Design system:** generated and refined with the `ui-ux-pro-max` skill at implementation time.

## 10. Known limitation (honest call-out)

The EMA-vs-Kronos backtest endpoints (`/api/backtest/ema | kronos`) are **single-symbol (BTC/USD) today**,
and Kronos is GPU-gated (falls back to the EMA baseline on CPU — already documented). Everything else in
Coin Detail runs per-symbol on existing endpoints. So the backtest comparison panel either renders only
for the symbol it supports, or a small backend `?symbol=` follow-up is added later. This panel is kept
**off the critical path**; the redesign does not depend on it being multi-symbol.

## 11. Proposed new file structure (frontend)

```
frontend/src/
  main.jsx                      # mounts <App/> inside HashRouter
  App.jsx                       # routes: / , /coin/:symbol , /settings ; token bootstrap
  api.js                        # unchanged (optionally trimmed)
  lib/utils.js                  # cn() helper (shadcn convention)
  components/ui/                # shadcn primitives (button, card, dialog, badge, ...)
  components/
    StatusStrip.jsx             # loop state + mode + equity/PnL + Start/Stop + health + broker banner
    CoinsGrid.jsx               # the per-coin grid
    CoinCard.jsx                # one coin card (status, position, last decision, actions)
    AddCoinDialog.jsx           # universe minus watchlist -> PUT /api/watchlist + arm
    RebalanceStrip.jsx          # compact rebalance status
    LiveJournal.jsx             # streaming decision feed
    detail/                     # restyled AutoDash panels, scoped per-symbol
      ChartPanel.jsx
      CurrentPositionPanel.jsx
      LiveStatsPanel.jsx
      BacktestComparisonPanel.jsx
      RecentTradesPanel.jsx
      JournalFeedPanel.jsx
      usePolling.js
    settings/
      BrokerConnectionPanel.jsx
      RebalancePanel.jsx
      AdvancedControls.jsx
    TokenGate.jsx
  pages/
    MissionControl.jsx          # #/
    CoinDetail.jsx              # #/coin/:symbol
    Settings.jsx                # #/settings
```

## 12. Visual direction

Dark **trading-terminal** aesthetic: deep neutral base, single semantic accent (emerald = up/positive,
red = down), monospaced numerics, dense-but-calm spacing. Exact palette / typography finalized during
implementation with `ui-ux-pro-max`; screenshots shared for sign-off before the Docker rebuild.

## 13. Testing & verification

- `cd frontend && npm run build` — green.
- **Playwright smoke** (mirrors the existing autodash smoke): status strip renders with live state; coins
  grid shows ≥1 card; Start/Stop toggles; Add-coin dialog opens and writes the watchlist; clicking a card
  opens Coin Detail; Settings broker panel renders. Save a screenshot artifact under `docs/`.
- Backend suite unchanged (frontend-only): **659 passed, 6 skipped** expected to hold.

## 14. Rollout

Per the standing Docker policy: `docker compose build swingbot && docker compose up -d swingbot`, then
live-verify on `:8000`. The running paper loop is interrupted by the rebuild (pre-authorized routine).

## 15. Future follow-ups (out of scope, noted)

- Backend `?symbol=` for the EMA-vs-Kronos backtest, so Coin Detail's comparison is multi-symbol.
- "Kronos: GPU required" degraded badge in the backtest panel (existing roadmap follow-up).
- Walk-forward + Sharpe-ratio backtesting over the Coinbase-backed deep-history archive (separate project).
- Decide whether to physically remove the headless Brain / Discovery / Usage-Agent backend subsystems.
