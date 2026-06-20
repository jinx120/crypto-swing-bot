# Autonomous-First UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the swingbot frontend around the autonomous loop — collapse 8 manual-era tabs into 3 hash routes (Mission Control / Coin Detail / Settings) with a Tailwind + shadcn/ui design system — with zero backend changes.

**Architecture:** A `HashRouter` app with three pages. Mission Control is the home: a status strip, a per-coin grid, a rebalance strip, and a live decision journal — all polling existing read endpoints. Coin Detail reuses the AutoDash panels, parameterized per strategy/symbol. Settings consolidates broker connection, rebalance config, and advanced controls. All pure view-logic is factored into a tested `lib/derive.js`; everything else verifies via `npm run build` + a Playwright smoke pass.

**Tech Stack:** React 18, Vite 5, `react-router-dom` v6 (HashRouter), Tailwind CSS v3, shadcn/ui-style primitives (Radix Dialog + `class-variance-authority` + `tailwind-merge` + `clsx` + `lucide-react`), `lightweight-charts` v5, Vitest + Testing Library for the pure helpers.

---

## Context for a cold code-gen agent

You are rebuilding **only** the frontend of `crypto-swing-bot` (`frontend/src/`). Read this whole preamble before Task 1; it is the orientation you would otherwise lack.

**What exists today (the starting point):**
- `frontend/src/main.jsx` calls `ensureToken()` then renders `<App/>`, importing the hand-rolled `theme.css`.
- `frontend/src/App.jsx` is a manual tab switcher over a custom `#/<tab>` hash scheme (`dashboard`, `auto`, `strategy`, `discover`, `brain`, `settings`, `health`, `guide`). It owns a polling loop and renders one page per tab.
- `frontend/src/api.js` exports `api` (every endpoint method you need already exists — see the inventory below), plus `getToken`/`setToken`/`ensureToken`. **You do not modify `api.js`** except the optional, non-required trim noted in the spec; treat it as a fixed dependency.
- `frontend/src/components/AutoDash/*` are the six panels (`ChartPanel`, `CurrentPositionPanel`, `LiveStatsPanel`, `RecentTradesPanel`, `BacktestComparisonPanel`, `JournalFeedPanel`) + `usePolling.js`. They are currently **hardcoded to the single-symbol `api.auto.*` live endpoints**. You will move + restyle + parameterize them per strategy/symbol.
- `frontend/src/pages/Settings.jsx` already contains a working schema-driven **Broker connection** form (Test / Save / Reconnect) and mounts `RebalancePanel` + `TokenGate`. You will extract its broker form into a standalone component.
- `frontend/src/components/{RebalancePanel,TokenGate}.jsx` are kept.

**House rules (non-negotiable):**
- Python venv is `.venv/bin/python` (plain `python`/`pytest` are not on PATH). You will not touch Python except to re-run the gate.
- **This is a frontend-only change. Do not edit anything under `src/swingbot/`.** The backend suite (`659 passed, 6 skipped`) must stay green and untouched.
- TDD applies to the pure helpers in `lib/derive.js` (Task 3) — real Vitest tests, red before green. UI components have no unit-test harness in this repo; their per-task gate is `npm run build` green, and they are smoke-tested end-to-end in Task 14.
- Frequent commits — one per task, after its gate passes.
- The repo tree carries unrelated uncommitted work (FVG/presets/graphify). Scope every `git add` to the exact files in the task. Never `git add -A`.
- Work on branch `core-engine` (already checked out).
- **Do not run a Docker rebuild until Task 14.** Rebuilds interrupt the live paper loop; the plan batches deploy + live-verify into the final task.

**Exact backend response shapes you will consume (verified against `src/swingbot/`):**

`GET /api/state` → `controller.status()`:
```jsonc
{
  "portfolio": { "mode": "paper", "running": true, "paused": false,
                 "equity": 10240.0, "deployed": 0.0, "deployed_frac": 0.0,
                 "open_positions": 1, "day_pnl": 12.3,
                 "kill_switch": { "active": false, "reason": "" } },
  "strategies": [
    { "name": "btc_trend", "symbol": "BTC/USD", "running": true,
      "live_eligible": false, "kind": "strategy", "label": "BTC trend",
      "probe_complete": false,
      "snapshot": { /* opaque */ },
      "position": { "symbol": "BTC/USD", "entry_price": 64000.0, "qty": 0.01,
                    "stop": 63000.0, "tp": 66000.0,
                    "mark_price": 64500.0, "mark_ts": "2026-06-20T10:42:00+00:00",
                    "unrealized": 5.0 } | null,
      "risk": { "kill_switch": { "active": false, "reason": "" },
                "consecutive_losses": 0 } | null }
  ],
  "pending_orders": [ { "strategy": "btc_trend", "symbol": "BTC/USD", "side": "buy",
                        "requested_qty": 0.01, "submitted_at": "...",
                        "client_order_id": "...", "broker_order_id": "..." } ]
}
```
`GET /api/health/trading` → `controller.trading_health()`:
```jsonc
{
  "status": "active" | "inactive" | "unhealthy",
  "lifecycle": { "mode": "paper", "running_flag": true, "thread_alive": true,
                 "running_actual": true, "running_desired": true,
                 "running_desired_error": null, "paused": false, "halted": false,
                 "startup_error": null },
  "last_cycle": { ...cycle... } | null,
  "last_decisions_by_strategy": {
     "btc_trend": { "strategy": "btc_trend", "bar_ts": "...",
                    "decision_code": "ENTER", "decision_reason": "ema fast crossed slow",
                    "decision_details": {...}, "started_at": "...", "completed_at": "..." } },
  "reliability": { "completed_cycles": 200, "cycle_completion_ratio": 0.98,
                   "stages": { "...": { "ratio": 1.0, "ok": 200, "failed": 0,
                   "skipped": 0, "samples": 200 } }, /* + window fields */ }
}
```
`GET /api/rebalance/status` → `{ "enabled": false, "mode": "soft", "allocations": [...],
   "last_rebalance_at": "", "next_eligible_at": "", "last_skip_reason": "" }`
`GET /api/rebalance/settings` → `{ "enabled": false, "mode": "soft", "min_interval_minutes": ..., ... }`
`GET /api/strategies` → `[ { "name","symbol","armed","live_eligible","kind","label" } ]`
`GET /api/universe` → `{ "symbols": ["BTC/USD", "ETH/USD", ...] }`
`GET /api/watchlist` → `{ "symbols": ["BTC/USD", "ETH/USD"] }`
`GET /api/journal?strategy=<name>` → `[ { "entry_ts","exit_ts","entry_price","exit_price",
   "qty","pnl","exit_reason","score_at_entry","regime_at_entry" } ]`  (closed trades)
`GET /api/metrics?strategy=<name>` → `{ "win_rate","total_pnl","sharpe","n_trades", ... }`
`GET /api/candles?symbol=<sym>&timeframe=<tf>&limit=<n>` → `{ "symbol","timeframe",
   "candles": [ { "time": <epoch>, "open","high","low","close","volume" } ] }`

**`api` methods already available (in `api.js`, do not re-add):**
`state()`, `journal(strategy?)`, `metrics(strategy?)`, `tradingHealth()`, `candles(symbol,timeframe,limit?)`,
`strategies()`, `arm(name)`, `disarm(name)`, `setLiveEligible(name,eligible)`,
`flattenStrategy(name)`, `control(action, body?)`, `universe()`, `watchlist()`, `setWatchlist(symbols)`,
`portfolioSettings()`, `setPortfolioSettings(patch)`,
`getRebalanceStatus()`, `getRebalanceSettings()`, `setRebalanceSettings(body)`,
`getRebalanceTargets()`, `setRebalanceTargets(body)`, `runRebalance()`,
`listBrokers()`, `setBrokerCreds(id,values)`, `testBroker(id,values,mode)`,
`setActiveBroker(id)`, `reconnectBroker()`, plus `getToken/setToken/ensureToken`.

**Control endpoints:** `POST /api/control/{start|stop|pause|resume|halt|reset}` (token-gated),
`POST /api/control/{name}/flatten` (token-gated, via `api.flattenStrategy(name)`).

**Deliberate deviations from the spec (resolved here, do not re-litigate):**
1. **Coin Detail routes by strategy *name*, not raw symbol** — `#/coin/:name` (e.g. `#/coin/btc_trend`), because symbols contain a `/` ("BTC/USD") which breaks hash path params. The page resolves the display symbol from `/api/state`. The spec's intent (per-coin deep dive) is preserved.
2. **shadcn primitives are hand-authored** (not via the `shadcn` CLI, which needs interactive prompts/network unavailable here). Only **Radix Dialog** is pulled in; selects/inputs are Tailwind-styled native elements. This still satisfies "shadcn/ui (Radix primitives)".
3. **Backtest panel stays single-symbol** (BTC/USD via `api.auto.backtest*`); for other coins it renders a one-line "single-symbol (BTC/USD) only" note — exactly the spec §10 escape hatch.

---

## Global Constraints

- **Frontend only.** No file under `src/swingbot/` changes. Backend gate `659 passed, 6 skipped` must hold (re-run in Task 14).
- **Branch:** `core-engine`. **No Docker rebuild before Task 14.** Scope every `git add` to the task's files (never `-A`).
- **Routing:** `react-router-dom` v6 `HashRouter`, exactly three routes: `/`, `/coin/:name`, `/settings`. Token bootstrap (`ensureToken()` in `main.jsx`) and the `TokenGate` fallback are preserved.
- **Design system:** Tailwind v3 + CSS-variable tokens (HSL) in `index.css`; the `cn()` helper from `lib/utils.js` on every styled component. Visual direction: dark trading-terminal — deep neutral base, emerald = up/positive, red = down, monospaced numerics. Hex values in Task 1 are a working baseline; refine with the `ui-ux-pro-max` skill if desired, but **token names are fixed** (later tasks reference them).
- **Polling cadence:** reuse `usePolling(fetcher, intervalMs)` — fast surfaces 3000ms, slow/cached surfaces 10000ms, backtest 60000ms (matches today's panels).
- **No placeholders / no dead text.** Every panel keeps its last good value on transient errors (that is what `usePolling` already does).
- **Verification per task:** `cd frontend && npm run build` is green; Task 3 also runs `npm run test`. Task 14 runs the Playwright smoke + the backend gate.

---

## File Structure

```
frontend/
  package.json                    # MODIFY: deps + "test" script
  tailwind.config.js              # CREATE
  postcss.config.js               # CREATE
  src/
    index.css                     # CREATE  (Tailwind directives + design tokens)
    theme.css                     # DELETE  (Task 13)
    main.jsx                      # MODIFY  (import index.css, mount HashRouter)
    App.jsx                       # REWRITE (routes + token bootstrap)
    api.js                        # UNCHANGED
    lib/
      utils.js                    # CREATE  (cn helper)
      derive.js                   # CREATE  (pure view logic, TDD)
      derive.test.js              # CREATE  (Vitest)
    components/
      ui/                         # CREATE  (shadcn-style primitives)
        button.jsx
        card.jsx
        badge.jsx
        dialog.jsx
        input.jsx
        label.jsx
      StatusStrip.jsx             # CREATE
      CoinsGrid.jsx               # CREATE
      CoinCard.jsx                # CREATE
      AddCoinDialog.jsx           # CREATE
      RebalanceStrip.jsx          # CREATE
      LiveJournal.jsx             # CREATE
      TokenGate.jsx               # KEEP (restyled inline in Task 12)
      RebalancePanel.jsx          # KEEP (wrapped in Task 12)
      detail/                     # CREATE (parameterized AutoDash panels)
        usePolling.js             # MOVE from components/AutoDash/
        ChartPanel.jsx
        CurrentPositionPanel.jsx
        LiveStatsPanel.jsx
        RecentTradesPanel.jsx
        BacktestComparisonPanel.jsx
        JournalFeedPanel.jsx
      settings/
        BrokerConnectionPanel.jsx # CREATE (extracted from pages/Settings.jsx)
        AdvancedControls.jsx      # CREATE
    pages/
      MissionControl.jsx          # CREATE  (#/)
      CoinDetail.jsx              # CREATE  (#/coin/:name)
      Settings.jsx                # REWRITE (#/settings)
      # DELETE (Task 13): Dashboard, Strategy, Discover, Brain, Health, Guide, AutoDashboard
    # DELETE (Task 13): components/{ChartPanel,ControlBar,Hint,JournalTable,LifecycleBanner,
    #   MetricsPanel,PendingOrders,PortfolioBanner,PositionGrid,PositionPanel,PresetGallery,
    #   ReliabilityPanel,RiskPanel,SignalPanel,StatusBanner,StrategyBuilder,StrategyCard,
    #   StrategyManager}.jsx ; components/AutoDash/* ; guide.md
```

---

### Task 1: Build tooling — Tailwind + tokens + `cn()` + Vitest

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/src/index.css`, `frontend/src/lib/utils.js`

**Interfaces:**
- Produces: Tailwind build pipeline; `cn(...classes)` from `lib/utils.js`; design tokens (CSS vars) consumed by every later component; `npm run test` (Vitest) runnable.

- [ ] **Step 1: Add dependencies and the test script to `package.json`**

Replace the whole file with:
```json
{
  "name": "swingbot-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "@radix-ui/react-dialog": "^1.1.1",
    "class-variance-authority": "^0.7.0",
    "clsx": "^2.1.1",
    "lightweight-charts": "^5.2.0",
    "lucide-react": "^0.439.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.0",
    "tailwind-merge": "^2.5.2"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.8",
    "@testing-library/react": "^16.0.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.19",
    "jsdom": "^25.0.0",
    "postcss": "^8.4.38",
    "tailwindcss": "^3.4.10",
    "vite": "^5.3.1",
    "vitest": "^2.0.5"
  }
}
```
Note `marked` is intentionally dropped (only the cut Guide page used it).

- [ ] **Step 2: Install**

Run: `cd frontend && npm install`
Expected: completes; `node_modules/tailwindcss` and `node_modules/vitest` exist.

- [ ] **Step 3: Create `postcss.config.js`**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

- [ ] **Step 4: Create `tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: 'hsl(var(--card))',
        'card-foreground': 'hsl(var(--card-foreground))',
        muted: 'hsl(var(--muted))',
        'muted-foreground': 'hsl(var(--muted-foreground))',
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        primary: 'hsl(var(--primary))',
        'primary-foreground': 'hsl(var(--primary-foreground))',
        accent: 'hsl(var(--accent))',
        'accent-foreground': 'hsl(var(--accent-foreground))',
        up: 'hsl(var(--up))',
        down: 'hsl(var(--down))',
        warn: 'hsl(var(--warn))',
      },
      borderRadius: { lg: 'var(--radius)', md: 'calc(var(--radius) - 2px)', sm: 'calc(var(--radius) - 4px)' },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
    },
  },
  plugins: [],
}
```

- [ ] **Step 5: Create `src/index.css` (Tailwind directives + trading-terminal tokens)**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --background: 222 24% 7%;
  --foreground: 210 16% 92%;
  --card: 222 22% 10%;
  --card-foreground: 210 16% 92%;
  --muted: 220 14% 16%;
  --muted-foreground: 215 14% 60%;
  --border: 220 14% 18%;
  --input: 220 14% 18%;
  --ring: 158 64% 42%;
  --primary: 158 64% 42%;
  --primary-foreground: 222 24% 7%;
  --accent: 220 14% 16%;
  --accent-foreground: 210 16% 92%;
  --up: 152 62% 50%;
  --down: 350 90% 60%;
  --warn: 38 92% 55%;
  --radius: 0.625rem;
}

* { border-color: hsl(var(--border)); }
html, body, #root { height: 100%; }
body {
  background: hsl(var(--background));
  color: hsl(var(--foreground));
  font-family: ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif;
  -webkit-font-smoothing: antialiased;
}
.tabular-nums { font-variant-numeric: tabular-nums; }
```

- [ ] **Step 6: Create `src/lib/utils.js`**

```js
import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}
```

- [ ] **Step 7: Verify build + test runner**

Run: `cd frontend && npm run build && npm run test`
Expected: build green; Vitest prints `No test files found` (exit 0 — acceptable at this stage) **or** passes. The old app still renders (it still imports `theme.css` via `main.jsx`; untouched here).

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tailwind.config.js \
        frontend/postcss.config.js frontend/src/index.css frontend/src/lib/utils.js
git commit -m "build(ui): add Tailwind + shadcn deps, design tokens, cn helper, Vitest"
```

---

### Task 2: shadcn-style UI primitives

**Files:**
- Create: `frontend/src/components/ui/{button,card,badge,dialog,input,label}.jsx`

**Interfaces:**
- Produces: `Button`, `Card`/`CardHeader`/`CardTitle`/`CardContent`/`CardFooter`, `Badge`, `Dialog`/`DialogTrigger`/`DialogContent`/`DialogHeader`/`DialogTitle`/`DialogClose`, `Input`, `Label`. All consume `cn()` and the Task 1 tokens.

- [ ] **Step 1: `components/ui/button.jsx`**

```jsx
import { cva } from 'class-variance-authority'
import { cn } from '../../lib/utils.js'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground hover:bg-primary/90',
        outline: 'border border-border bg-transparent hover:bg-accent hover:text-accent-foreground',
        ghost: 'hover:bg-accent hover:text-accent-foreground',
        danger: 'bg-down text-white hover:bg-down/90',
      },
      size: {
        default: 'h-9 px-4 py-2',
        sm: 'h-8 rounded-md px-3 text-xs',
        icon: 'h-9 w-9',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export function Button({ className, variant, size, ...props }) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />
}
export { buttonVariants }
```

- [ ] **Step 2: `components/ui/card.jsx`**

```jsx
import { cn } from '../../lib/utils.js'

export function Card({ className, ...props }) {
  return <div className={cn('rounded-lg border border-border bg-card text-card-foreground shadow-sm', className)} {...props} />
}
export function CardHeader({ className, ...props }) {
  return <div className={cn('flex flex-col gap-1 p-4', className)} {...props} />
}
export function CardTitle({ className, ...props }) {
  return <h3 className={cn('text-sm font-semibold tracking-tight text-muted-foreground uppercase', className)} {...props} />
}
export function CardContent({ className, ...props }) {
  return <div className={cn('p-4 pt-0', className)} {...props} />
}
export function CardFooter({ className, ...props }) {
  return <div className={cn('flex items-center p-4 pt-0', className)} {...props} />
}
```

- [ ] **Step 3: `components/ui/badge.jsx`**

```jsx
import { cva } from 'class-variance-authority'
import { cn } from '../../lib/utils.js'

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-muted text-muted-foreground',
        up: 'border-transparent bg-up/15 text-up',
        down: 'border-transparent bg-down/15 text-down',
        warn: 'border-transparent bg-warn/15 text-warn',
        outline: 'border-border text-foreground',
      },
    },
    defaultVariants: { variant: 'default' },
  },
)

export function Badge({ className, variant, ...props }) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
```

- [ ] **Step 4: `components/ui/dialog.jsx`**

```jsx
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils.js'

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close

export function DialogContent({ className, children, ...props }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
      <DialogPrimitive.Content
        className={cn(
          'fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-card p-5 shadow-lg',
          className,
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}
export function DialogHeader({ className, ...props }) {
  return <div className={cn('mb-3 flex flex-col gap-1', className)} {...props} />
}
export function DialogTitle({ className, ...props }) {
  return <DialogPrimitive.Title className={cn('text-base font-semibold', className)} {...props} />
}
```

- [ ] **Step 5: `components/ui/input.jsx` and `components/ui/label.jsx`**

`input.jsx`:
```jsx
import { cn } from '../../lib/utils.js'

export function Input({ className, ...props }) {
  return (
    <input
      className={cn(
        'flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50',
        className,
      )}
      {...props}
    />
  )
}
```
`label.jsx`:
```jsx
import { cn } from '../../lib/utils.js'

export function Label({ className, ...props }) {
  return <label className={cn('text-xs font-medium text-muted-foreground', className)} {...props} />
}
```

- [ ] **Step 6: Verify build**

Run: `cd frontend && npm run build`
Expected: green (primitives compile; not yet imported anywhere).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/ui
git commit -m "feat(ui): add shadcn-style primitives (button, card, badge, dialog, input, label)"
```

---

### Task 3: Pure view logic — `lib/derive.js` (TDD)

**Files:**
- Create: `frontend/src/lib/derive.js`
- Test: `frontend/src/lib/derive.test.js`
- Modify: `frontend/vite.config.js` if no Vitest config block exists (add `test` block); otherwise create it.

**Interfaces:**
- Produces (exact signatures consumed by Tasks 4–12):
  - `loopState(health) -> 'RUNNING' | 'PAUSED' | 'STOPPED'`
  - `modeBadge(state) -> 'PAPER' | 'LIVE'`
  - `equityOf(state) -> number | null`
  - `dayPnl(state) -> number | null`
  - `dayPnlPct(state) -> number | null`
  - `reliabilityPct(health) -> number | null`
  - `brokerUnauthorized(health) -> boolean`
  - `cardStatus(strategy) -> 'long' | 'short' | 'flat' | 'armed'`
  - `availableToAdd(universe, watchlist) -> string[]`
  - `lastDecision(health, name) -> { code: string, reason: string } | null`

- [ ] **Step 1: Ensure Vitest config exists**

Read `frontend/vite.config.js`. If it lacks a `test` block, set the file to:
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom', globals: true },
})
```
(Preserve any existing `server.proxy` block if present — append `test` alongside it.)

- [ ] **Step 2: Write the failing test `src/lib/derive.test.js`**

```js
import { describe, it, expect } from 'vitest'
import {
  loopState, modeBadge, equityOf, dayPnl, dayPnlPct, reliabilityPct,
  brokerUnauthorized, cardStatus, availableToAdd, lastDecision,
} from './derive.js'

describe('loopState', () => {
  it('RUNNING when thread alive and not paused', () => {
    expect(loopState({ lifecycle: { running_actual: true, paused: false, halted: false } })).toBe('RUNNING')
  })
  it('PAUSED when paused or halted', () => {
    expect(loopState({ lifecycle: { running_actual: true, paused: true } })).toBe('PAUSED')
    expect(loopState({ lifecycle: { running_actual: true, halted: true } })).toBe('PAUSED')
  })
  it('STOPPED when no thread', () => {
    expect(loopState({ lifecycle: { running_actual: false } })).toBe('STOPPED')
    expect(loopState(null)).toBe('STOPPED')
  })
})

describe('modeBadge', () => {
  it('uppercases mode, defaults PAPER', () => {
    expect(modeBadge({ portfolio: { mode: 'live' } })).toBe('LIVE')
    expect(modeBadge({})).toBe('PAPER')
  })
})

describe('equity/pnl', () => {
  it('reads equity and day pnl', () => {
    const s = { portfolio: { equity: 10000, day_pnl: 210 } }
    expect(equityOf(s)).toBe(10000)
    expect(dayPnl(s)).toBe(210)
    expect(dayPnlPct(s)).toBeCloseTo(2.1, 5)
  })
  it('null-safe', () => {
    expect(equityOf({})).toBe(null)
    expect(dayPnlPct({ portfolio: { equity: 0, day_pnl: 5 } })).toBe(null)
  })
})

describe('reliabilityPct', () => {
  it('scales ratio to percent', () => {
    expect(reliabilityPct({ reliability: { cycle_completion_ratio: 0.98 } })).toBeCloseTo(98)
    expect(reliabilityPct({ reliability: { cycle_completion_ratio: null } })).toBe(null)
    expect(reliabilityPct({})).toBe(null)
  })
})

describe('brokerUnauthorized', () => {
  it('true on auth-flavored startup_error', () => {
    expect(brokerUnauthorized({ lifecycle: { startup_error: 'unauthorized' } })).toBe(true)
    expect(brokerUnauthorized({ lifecycle: { startup_error: 'missing credentials' } })).toBe(true)
  })
  it('false otherwise', () => {
    expect(brokerUnauthorized({ lifecycle: { startup_error: null } })).toBe(false)
    expect(brokerUnauthorized({ lifecycle: { startup_error: 'no armed strategies' } })).toBe(false)
    expect(brokerUnauthorized(null)).toBe(false)
  })
})

describe('cardStatus', () => {
  it('long/short/flat/armed', () => {
    expect(cardStatus({ running: true, position: { qty: 0.01 } })).toBe('long')
    expect(cardStatus({ running: true, position: { qty: -0.01 } })).toBe('short')
    expect(cardStatus({ running: true, position: null })).toBe('flat')
    expect(cardStatus({ running: false, position: null })).toBe('armed')
  })
})

describe('availableToAdd', () => {
  it('universe minus watchlist', () => {
    expect(availableToAdd({ symbols: ['BTC/USD', 'ETH/USD', 'SOL/USD'] }, { symbols: ['BTC/USD'] }))
      .toEqual(['ETH/USD', 'SOL/USD'])
    expect(availableToAdd(null, null)).toEqual([])
  })
})

describe('lastDecision', () => {
  it('maps code+reason', () => {
    const h = { last_decisions_by_strategy: { btc_trend: { decision_code: 'ENTER', decision_reason: 'xover' } } }
    expect(lastDecision(h, 'btc_trend')).toEqual({ code: 'ENTER', reason: 'xover' })
    expect(lastDecision(h, 'eth_trend')).toBe(null)
    expect(lastDecision(null, 'x')).toBe(null)
  })
})
```

- [ ] **Step 3: Run the test, verify it fails**

Run: `cd frontend && npm run test`
Expected: FAIL — `Failed to resolve import "./derive.js"`.

- [ ] **Step 4: Implement `src/lib/derive.js`**

```js
// Pure view-logic derived from the backend response shapes. No React, no I/O.

export function loopState(health) {
  const lc = health?.lifecycle
  if (!lc) return 'STOPPED'
  if (lc.paused || lc.halted) return 'PAUSED'
  if (lc.running_actual) return 'RUNNING'
  return 'STOPPED'
}

export function modeBadge(state) {
  return String(state?.portfolio?.mode || 'paper').toUpperCase()
}

export function equityOf(state) {
  const e = state?.portfolio?.equity
  return typeof e === 'number' ? e : null
}

export function dayPnl(state) {
  const p = state?.portfolio?.day_pnl
  return typeof p === 'number' ? p : null
}

export function dayPnlPct(state) {
  const eq = equityOf(state)
  const p = dayPnl(state)
  if (eq == null || p == null || eq === 0) return null
  return (p / eq) * 100
}

export function reliabilityPct(health) {
  const r = health?.reliability?.cycle_completion_ratio
  return typeof r === 'number' ? r * 100 : null
}

const AUTH_RE = /unauthor|credential|forbidden|401|403|invalid key/i

export function brokerUnauthorized(health) {
  const err = health?.lifecycle?.startup_error
  return !!(err && AUTH_RE.test(err))
}

export function cardStatus(strategy) {
  const qty = strategy?.position?.qty
  if (typeof qty === 'number' && qty > 0) return 'long'
  if (typeof qty === 'number' && qty < 0) return 'short'
  if (strategy?.running) return 'flat'
  return 'armed'
}

export function availableToAdd(universe, watchlist) {
  const all = universe?.symbols || []
  const have = new Set(watchlist?.symbols || [])
  return all.filter((s) => !have.has(s))
}

export function lastDecision(health, name) {
  const d = health?.last_decisions_by_strategy?.[name]
  if (!d) return null
  return { code: d.decision_code, reason: d.decision_reason }
}
```

- [ ] **Step 5: Run the test, verify it passes**

Run: `cd frontend && npm run test`
Expected: PASS — all `derive.test.js` cases green.

- [ ] **Step 6: Build sanity**

Run: `cd frontend && npm run build`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/lib/derive.js frontend/src/lib/derive.test.js frontend/vite.config.js
git commit -m "feat(ui): add tested pure view-logic helpers (lib/derive)"
```

---

### Task 4: Router shell + token bootstrap (the switch-over)

**Files:**
- Rewrite: `frontend/src/App.jsx`
- Modify: `frontend/src/main.jsx`
- Create: placeholder `frontend/src/pages/{MissionControl,CoinDetail,Settings}.jsx` (filled in later tasks)

**Interfaces:**
- Consumes: `ensureToken` (already called in `main.jsx`).
- Produces: `<App/>` mounting `HashRouter` with routes `/`, `/coin/:name`, `/settings`; a top `<nav>` (brand + links); `TokenGate` fallback preserved on Settings.

> This task replaces the manual-trading app shell. The old pages still exist on disk (deleted in Task 13) but are no longer mounted.

- [ ] **Step 1: Create placeholder pages so routes resolve**

`src/pages/MissionControl.jsx`:
```jsx
export default function MissionControl() {
  return <div className="mx-auto max-w-6xl p-4 text-muted-foreground">Mission Control</div>
}
```
`src/pages/CoinDetail.jsx`:
```jsx
import { useParams } from 'react-router-dom'
export default function CoinDetail() {
  const { name } = useParams()
  return <div className="mx-auto max-w-6xl p-4 text-muted-foreground">Coin Detail: {name}</div>
}
```
`src/pages/Settings.jsx` (placeholder — full version in Task 12):
```jsx
export default function Settings() {
  return <div className="mx-auto max-w-6xl p-4 text-muted-foreground">Settings</div>
}
```

- [ ] **Step 2: Rewrite `src/App.jsx`**

```jsx
import { HashRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Activity, Settings as SettingsIcon } from 'lucide-react'
import { cn } from './lib/utils.js'
import MissionControl from './pages/MissionControl.jsx'
import CoinDetail from './pages/CoinDetail.jsx'
import Settings from './pages/Settings.jsx'

function TopNav() {
  const link = ({ isActive }) =>
    cn('rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:text-foreground',
       isActive && 'bg-accent text-foreground')
  return (
    <nav className="sticky top-0 z-40 flex items-center gap-2 border-b border-border bg-background/80 px-4 py-2 backdrop-blur">
      <span className="mr-2 flex items-center gap-1.5 font-semibold">
        <Activity className="h-4 w-4 text-primary" /> SwingBot
      </span>
      <NavLink to="/" end className={link}>Mission Control</NavLink>
      <NavLink to="/settings" className={link}>
        <span className="inline-flex items-center gap-1"><SettingsIcon className="h-3.5 w-3.5" /> Settings</span>
      </NavLink>
    </nav>
  )
}

export default function App() {
  return (
    <HashRouter>
      <TopNav />
      <Routes>
        <Route path="/" element={<MissionControl />} />
        <Route path="/coin/:name" element={<CoinDetail />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<MissionControl />} />
      </Routes>
    </HashRouter>
  )
}
```

- [ ] **Step 3: Update `src/main.jsx` to import the Tailwind stylesheet**

```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { ensureToken } from './api.js'
import './index.css'

ensureToken().finally(() => {
  ReactDOM.createRoot(document.getElementById('root')).render(
    <React.StrictMode><App /></React.StrictMode>
  )
})
```
(Only the stylesheet import changes: `./theme.css` → `./index.css`. `theme.css` is deleted in Task 13.)

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: green. The bundle no longer imports `theme.css`; the three placeholder routes resolve.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.jsx frontend/src/main.jsx \
        frontend/src/pages/MissionControl.jsx frontend/src/pages/CoinDetail.jsx frontend/src/pages/Settings.jsx
git commit -m "feat(ui): switch app shell to HashRouter (Mission Control / Coin Detail / Settings)"
```

---

### Task 5: StatusStrip

**Files:**
- Create: `frontend/src/components/StatusStrip.jsx`

**Interfaces:**
- Consumes: `loopState`, `modeBadge`, `equityOf`, `dayPnl`, `dayPnlPct`, `reliabilityPct`, `brokerUnauthorized` from `lib/derive.js`; `api.state`, `api.tradingHealth`, `api.control`; `Button`, `Badge`.
- Produces: `<StatusStrip state={...} health={...} onChange={fn} />` — loop state + mode + equity/PnL + Start/Stop toggle + health dots + broker-unauthorized banner.

- [ ] **Step 1: Implement `components/StatusStrip.jsx`**

```jsx
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { api } from '../api.js'
import { Button } from './ui/button.jsx'
import { Badge } from './ui/badge.jsx'
import { cn } from '../lib/utils.js'
import {
  loopState, modeBadge, equityOf, dayPnl, dayPnlPct, reliabilityPct, brokerUnauthorized,
} from '../lib/derive.js'

function Dot({ ok, label }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <span className={cn('h-1.5 w-1.5 rounded-full', ok ? 'bg-up' : 'bg-down')} /> {label}
    </span>
  )
}

export default function StatusStrip({ state, health, onChange }) {
  const [busy, setBusy] = useState(false)
  const loop = loopState(health)
  const running = loop === 'RUNNING'
  const eq = equityOf(state)
  const pnl = dayPnl(state)
  const pct = dayPnlPct(state)
  const rel = reliabilityPct(health)
  const noBroker = brokerUnauthorized(health)

  const toggle = async () => {
    setBusy(true)
    try { await api.control(running ? 'stop' : 'start'); await onChange?.() }
    catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  const loopColor = loop === 'RUNNING' ? 'bg-up' : loop === 'PAUSED' ? 'bg-warn' : 'bg-muted-foreground'

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2">
          <span className={cn('h-2.5 w-2.5 rounded-full', loopColor)} />
          <span className="font-semibold">{loop}</span>
          <Badge variant="outline">{modeBadge(state)}</Badge>
        </div>
        <div className="text-sm">
          equity <span className="font-mono tabular-nums font-semibold">
            {eq == null ? '—' : `$${eq.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          </span>
        </div>
        <div className="text-sm">
          today{' '}
          <span className={cn('font-mono tabular-nums font-semibold', (pnl ?? 0) >= 0 ? 'text-up' : 'text-down')}>
            {pnl == null ? '—' : `${pnl >= 0 ? '▲ +' : '▼ '}${pnl.toFixed(2)}`}
            {pct != null && ` (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%)`}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-4">
          <Dot ok={!!state} label="backend" />
          <Dot ok={!noBroker} label="broker" />
          <Dot ok={rel == null ? true : rel >= 90} label={`reliability ${rel == null ? '—' : rel.toFixed(0) + '%'}`} />
          <Button variant={running ? 'danger' : 'default'} size="sm" disabled={busy} onClick={toggle}>
            {running ? 'Stop' : 'Start'}
          </Button>
        </div>
      </div>
      {noBroker && (
        <Link to="/settings"
          className="flex items-center gap-2 rounded-lg border border-warn/40 bg-warn/10 px-4 py-2 text-sm text-warn">
          <AlertTriangle className="h-4 w-4" />
          Broker not connected — fix in Settings →
        </Link>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/StatusStrip.jsx
git commit -m "feat(ui): StatusStrip (loop state, mode, equity/PnL, Start/Stop, broker banner)"
```

---

### Task 6: CoinCard + CoinsGrid

**Files:**
- Create: `frontend/src/components/CoinCard.jsx`, `frontend/src/components/CoinsGrid.jsx`

**Interfaces:**
- Consumes: `cardStatus`, `lastDecision`; `api.arm`, `api.disarm`, `api.flattenStrategy`; `Card*`, `Badge`, `Button`.
- Produces:
  - `<CoinCard strategy={...} health={...} onChange={fn} />`
  - `<CoinsGrid state={...} health={...} onChange={fn} onAdd={fn} />` (renders one `CoinCard` per `state.strategies`, plus the "+ Add coin" trigger slot via `onAdd`).

- [ ] **Step 1: Implement `components/CoinCard.jsx`**

```jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { Card, CardContent } from './ui/card.jsx'
import { Badge } from './ui/badge.jsx'
import { Button } from './ui/button.jsx'
import { cn } from '../lib/utils.js'
import { cardStatus, lastDecision } from '../lib/derive.js'

const STATUS_VARIANT = { long: 'up', short: 'down', flat: 'default', armed: 'outline' }

export default function CoinCard({ strategy, health, onChange }) {
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const status = cardStatus(strategy)
  const pos = strategy.position
  const unreal = pos?.unrealized
  const decision = lastDecision(health, strategy.name)
  const hasPosition = !!pos && status !== 'armed'

  const act = async (fn) => {
    setBusy(true)
    try { await fn(); await onChange?.() } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  return (
    <Card
      className="cursor-pointer transition-colors hover:border-primary/50"
      onClick={() => nav(`/coin/${encodeURIComponent(strategy.name)}`)}
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <span className="font-semibold">{strategy.symbol || strategy.label}</span>
          <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>
        </div>
        <div className="font-mono tabular-nums text-sm">
          {hasPosition ? (
            <>
              <div className="text-muted-foreground">
                {Number(pos.qty)} @ {Number(pos.entry_price).toFixed(2)}
              </div>
              <div className={cn('text-lg font-semibold', (unreal ?? 0) >= 0 ? 'text-up' : 'text-down')}>
                {unreal == null ? '—' : `${unreal >= 0 ? '+' : ''}${unreal.toFixed(2)}`}
              </div>
            </>
          ) : (
            <div className="text-muted-foreground">—</div>
          )}
        </div>
        <div className="min-h-[2.5rem] text-xs text-muted-foreground">
          {decision ? <><b className="text-foreground">{decision.code}</b> · {decision.reason}</> : 'no recent decision'}
        </div>
        <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
          {status === 'armed'
            ? <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => api.arm(strategy.name))}>arm</Button>
            : <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => api.disarm(strategy.name))}>disarm</Button>}
          {hasPosition &&
            <Button size="sm" variant="danger" disabled={busy} onClick={() => act(() => api.flattenStrategy(strategy.name))}>flatten</Button>}
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Implement `components/CoinsGrid.jsx`**

```jsx
import { Plus } from 'lucide-react'
import CoinCard from './CoinCard.jsx'
import { Button } from './ui/button.jsx'

export default function CoinsGrid({ state, health, onChange, onAdd }) {
  const strategies = state?.strategies || []
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Coins</h2>
        <Button size="sm" variant="outline" onClick={onAdd}>
          <Plus className="h-3.5 w-3.5" /> Add coin
        </Button>
      </div>
      {strategies.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          No coins armed yet. Use “Add coin” to start trading a symbol.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {strategies.map((s) => (
            <CoinCard key={s.name} strategy={s} health={health} onChange={onChange} />
          ))}
        </div>
      )}
    </section>
  )
}
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: green.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/CoinCard.jsx frontend/src/components/CoinsGrid.jsx
git commit -m "feat(ui): per-coin grid (CoinCard + CoinsGrid) with arm/disarm/flatten"
```

---

### Task 7: AddCoinDialog

**Files:**
- Create: `frontend/src/components/AddCoinDialog.jsx`

**Interfaces:**
- Consumes: `availableToAdd`; `api.universe`, `api.watchlist`, `api.setWatchlist`, `api.strategies`, `api.arm`; `Dialog*`, `Button`.
- Produces: `<AddCoinDialog open={bool} onOpenChange={fn} onAdded={fn} />` — lists universe-minus-watchlist; selecting a symbol writes the watchlist and arms its managed strategy if one exists.

- [ ] **Step 1: Implement `components/AddCoinDialog.jsx`**

```jsx
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog.jsx'
import { Button } from './ui/button.jsx'
import { availableToAdd } from '../lib/derive.js'

export default function AddCoinDialog({ open, onOpenChange, onAdded }) {
  const [options, setOptions] = useState([])
  const [watchlist, setWatchlist] = useState({ symbols: [] })
  const [strategies, setStrategies] = useState([])
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!open) return
    setErr('')
    Promise.all([api.universe(), api.watchlist(), api.strategies()])
      .then(([u, w, s]) => { setOptions(availableToAdd(u, w)); setWatchlist(w); setStrategies(s) })
      .catch((e) => setErr(e.message))
  }, [open])

  const add = async (symbol) => {
    setBusy(symbol); setErr('')
    try {
      await api.setWatchlist([...(watchlist.symbols || []), symbol])
      const match = strategies.find((st) => st.symbol === symbol)
      if (match) await api.arm(match.name)
      await onAdded?.()
      onOpenChange(false)
    } catch (e) { setErr(e.message) } finally { setBusy('') }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add coin</DialogTitle></DialogHeader>
        {err && <div className="mb-2 rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}
        <div className="max-h-72 space-y-1 overflow-y-auto">
          {options.length === 0
            ? <div className="p-4 text-center text-sm text-muted-foreground">All available symbols are already added.</div>
            : options.map((sym) => (
              <button key={sym} disabled={busy === sym} onClick={() => add(sym)}
                className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-50">
                <span className="font-medium">{sym}</span>
                <span className="text-xs text-muted-foreground">{busy === sym ? 'adding…' : 'add →'}</span>
              </button>
            ))}
        </div>
        <div className="mt-3 flex justify-end">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Close</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AddCoinDialog.jsx
git commit -m "feat(ui): AddCoinDialog (universe minus watchlist -> watchlist + arm)"
```

---

### Task 8: RebalanceStrip

**Files:**
- Create: `frontend/src/components/RebalanceStrip.jsx`

**Interfaces:**
- Consumes: `api.getRebalanceStatus`; `usePolling` (from `components/detail/usePolling.js` — but that move happens in Task 11; until then import the existing `components/AutoDash/usePolling.js`). To avoid an ordering hazard, this component imports the **shared** hook by its final path and Task 11 guarantees the file exists. **Resolution:** import from `../components/AutoDash/usePolling.js` here and update the import in Task 11 when the file moves. Simpler: this component uses a local `useEffect` poll (below) so it has no cross-task path dependency.
- Produces: `<RebalanceStrip />` — compact read of `/api/rebalance/status` with a "configure →" link to Settings.

- [ ] **Step 1: Implement `components/RebalanceStrip.jsx` (self-contained polling, no shared-hook dependency)**

```jsx
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Scale } from 'lucide-react'
import { api } from '../api.js'
import { Badge } from './ui/badge.jsx'

export default function RebalanceStrip() {
  const [status, setStatus] = useState(null)
  useEffect(() => {
    let alive = true
    const tick = () => api.getRebalanceStatus().then((s) => { if (alive) setStatus(s) }).catch(() => {})
    tick()
    const id = setInterval(tick, 10000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const enabled = status?.enabled
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-2.5 text-sm">
      <Scale className="h-4 w-4 text-muted-foreground" />
      <span className="font-medium">Rebalance</span>
      {!enabled ? (
        <span className="text-muted-foreground">off</span>
      ) : (
        <>
          <Badge variant="outline">{status.mode}</Badge>
          {status.last_skip_reason
            ? <span className="text-muted-foreground">{status.last_skip_reason}</span>
            : <span className="text-up">on target</span>}
          {status.next_eligible_at &&
            <span className="text-muted-foreground">next ≥ {status.next_eligible_at.slice(11, 16)}</span>}
        </>
      )}
      <Link to="/settings" className="ml-auto text-muted-foreground hover:text-foreground">configure →</Link>
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/RebalanceStrip.jsx
git commit -m "feat(ui): RebalanceStrip (compact rebalance status + configure link)"
```

---

### Task 9: LiveJournal

**Files:**
- Create: `frontend/src/components/LiveJournal.jsx`

**Interfaces:**
- Consumes: `reliabilityPct`; `health.last_decisions_by_strategy`; `Card*`.
- Produces: `<LiveJournal health={...} />` — streaming decision feed (latest decision per strategy, newest first) + reliability summary.

- [ ] **Step 1: Implement `components/LiveJournal.jsx`**

```jsx
import { Card, CardContent, CardHeader, CardTitle } from './ui/card.jsx'
import { reliabilityPct } from '../lib/derive.js'

export default function LiveJournal({ health }) {
  const byStrat = health?.last_decisions_by_strategy || {}
  const rows = Object.values(byStrat)
    .map((d) => ({
      ts: d.bar_ts || d.completed_at || '',
      strategy: d.strategy,
      code: d.decision_code,
      reason: d.decision_reason,
    }))
    .sort((a, b) => (a.ts < b.ts ? 1 : -1))
  const rel = reliabilityPct(health)

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Decision Journal (live)</CardTitle>
        <span className="text-xs text-muted-foreground">
          reliability {rel == null ? '—' : `${rel.toFixed(0)}%`}
        </span>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <div className="text-sm text-muted-foreground">No decisions yet.</div>
        ) : (
          <div className="divide-y divide-border">
            {rows.map((r, i) => (
              <div key={i} className="flex items-baseline gap-3 py-1.5 text-sm">
                <span className="w-12 shrink-0 font-mono text-xs text-muted-foreground">
                  {(r.ts || '').slice(11, 16)}
                </span>
                <span className="w-24 shrink-0 font-medium">{r.strategy}</span>
                <span className="w-16 shrink-0 font-semibold">{r.code}</span>
                <span className="text-muted-foreground">{r.reason}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LiveJournal.jsx
git commit -m "feat(ui): LiveJournal (per-strategy decision feed + reliability)"
```

---

### Task 10: MissionControl page (compose)

**Files:**
- Rewrite: `frontend/src/pages/MissionControl.jsx`

**Interfaces:**
- Consumes: `StatusStrip`, `CoinsGrid`, `RebalanceStrip`, `LiveJournal`, `AddCoinDialog`; `api.state`, `api.tradingHealth`.
- Produces: the `#/` page — owns the poll loop for `state` + `health`, renders the four sections, and hosts the Add-coin dialog.

- [ ] **Step 1: Implement `pages/MissionControl.jsx`**

```jsx
import { useCallback, useEffect, useState } from 'react'
import StatusStrip from '../components/StatusStrip.jsx'
import CoinsGrid from '../components/CoinsGrid.jsx'
import RebalanceStrip from '../components/RebalanceStrip.jsx'
import LiveJournal from '../components/LiveJournal.jsx'
import AddCoinDialog from '../components/AddCoinDialog.jsx'
import { api } from '../api.js'

export default function MissionControl() {
  const [state, setState] = useState(null)
  const [health, setHealth] = useState(null)
  const [addOpen, setAddOpen] = useState(false)

  const refresh = useCallback(async () => {
    try { setState(await api.state()) } catch { /* keep last */ }
    try { setHealth(await api.tradingHealth()) } catch { /* keep last */ }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 3000)
    return () => clearInterval(id)
  }, [refresh])

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <StatusStrip state={state} health={health} onChange={refresh} />
      <CoinsGrid state={state} health={health} onChange={refresh} onAdd={() => setAddOpen(true)} />
      <RebalanceStrip />
      <LiveJournal health={health} />
      <AddCoinDialog open={addOpen} onOpenChange={setAddOpen} onAdded={refresh} />
    </div>
  )
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: green.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/MissionControl.jsx
git commit -m "feat(ui): Mission Control home (status + coins + rebalance + journal)"
```

---

### Task 11: Per-symbol detail panels + Coin Detail page

**Files:**
- Create (move): `frontend/src/components/detail/usePolling.js` (copy of `components/AutoDash/usePolling.js`)
- Create: `frontend/src/components/detail/{ChartPanel,CurrentPositionPanel,LiveStatsPanel,RecentTradesPanel,BacktestComparisonPanel,JournalFeedPanel}.jsx`
- Rewrite: `frontend/src/pages/CoinDetail.jsx`

**Interfaces:**
- Consumes: `api.candles(symbol, timeframe)`, `api.journal(strategy)`, `api.metrics(strategy)`, `api.state`, `api.auto.backtestEma/Kronos`, `api.arm/disarm/flattenStrategy/setWatchlist/watchlist`; `usePolling`; `Card*`, `Button`, `Badge`; `lightweight-charts`.
- Produces: restyled, **per-strategy/per-symbol** panels and the `#/coin/:name` page (resolves symbol from `/api/state`).

- [ ] **Step 1: Create `components/detail/usePolling.js`**

Copy the existing hook verbatim:
```js
import { useEffect, useRef, useState } from 'react'

export default function usePolling(fetcher, intervalMs = 10000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fetcher)
  fnRef.current = fetcher

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const d = await fnRef.current()
        if (alive) { setData(d); setError(''); setLoading(false) }
      } catch (e) {
        if (alive) { setError(e.message || 'error'); setLoading(false) }
      }
    }
    tick()
    const id = setInterval(tick, intervalMs)
    return () => { alive = false; clearInterval(id) }
  }, [intervalMs])

  return { data, error, loading }
}
```

- [ ] **Step 2: `components/detail/ChartPanel.jsx` (per symbol + per-strategy markers)**

```jsx
import { useEffect, useMemo, useRef } from 'react'
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts'
import { api } from '../../api.js'
import usePolling from './usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

const UP = '#2bd97a'
const DOWN = '#ff4d6d'

export default function ChartPanel({ symbol, strategy, timeframe = '15m' }) {
  const candlesFetcher = useMemo(() => () => api.candles(symbol, timeframe, 500), [symbol, timeframe])
  const tradesFetcher = useMemo(() => () => api.journal(strategy), [strategy])
  const { data: candleResp } = usePolling(candlesFetcher, 10000)
  const { data: trades } = usePolling(tradesFetcher, 10000)
  const elRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)

  useEffect(() => {
    if (!elRef.current || chartRef.current) return
    const chart = createChart(elRef.current, {
      height: 360, layout: { background: { color: 'transparent' }, textColor: '#9aa4b2' },
      grid: { vertLines: { color: '#1c2530' }, horzLines: { color: '#1c2530' } },
      timeScale: { timeVisible: true },
    })
    const series = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, borderVisible: false, wickUpColor: UP, wickDownColor: DOWN,
    })
    chartRef.current = chart; seriesRef.current = series
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null }
  }, [])

  useEffect(() => {
    if (!seriesRef.current) return
    const candles = candleResp?.candles || []
    seriesRef.current.setData(candles.map((c) => ({
      time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })))
    const markers = (trades || [])
      .filter((t) => t.exit_ts)
      .map((t) => ({
        time: Math.floor(new Date(t.exit_ts).getTime() / 1000),
        position: 'aboveBar', color: t.pnl >= 0 ? UP : DOWN, shape: 'circle',
        text: (t.pnl >= 0 ? '+' : '') + Number(t.pnl).toFixed(0),
      }))
      .sort((a, b) => a.time - b.time)
    createSeriesMarkers(seriesRef.current, markers)
    chartRef.current?.timeScale().fitContent()
  }, [candleResp, trades])

  return (
    <Card>
      <CardHeader><CardTitle>{symbol} candles</CardTitle></CardHeader>
      <CardContent><div ref={elRef} style={{ width: '100%' }} /></CardContent>
    </Card>
  )
}
```

- [ ] **Step 3: `components/detail/CurrentPositionPanel.jsx` (from state)**

```jsx
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

function Row({ k, v }) {
  return <div className="flex justify-between"><span className="text-muted-foreground">{k}</span><span className="font-mono tabular-nums">{v}</span></div>
}

export default function CurrentPositionPanel({ strategy: strat }) {
  const pos = strat?.position
  return (
    <Card>
      <CardHeader><CardTitle>Current position</CardTitle></CardHeader>
      <CardContent className="space-y-1 text-sm">
        {!pos ? <div className="text-muted-foreground">No open position (flat).</div> : (
          <>
            <Row k="Symbol" v={pos.symbol} />
            <Row k="Entry" v={Number(pos.entry_price).toFixed(2)} />
            <Row k="Qty" v={Number(pos.qty)} />
            <Row k="Mark" v={pos.mark_price != null ? Number(pos.mark_price).toFixed(2) : '—'} />
            <Row k="Unrealized" v={pos.unrealized != null ? Number(pos.unrealized).toFixed(2) : '—'} />
            <Row k="Stop" v={pos.stop != null ? Number(pos.stop).toFixed(2) : '—'} />
            <Row k="Target" v={pos.tp != null ? Number(pos.tp).toFixed(2) : '—'} />
          </>
        )}
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 4: `components/detail/LiveStatsPanel.jsx` (per-strategy metrics)**

```jsx
import { useMemo } from 'react'
import { api } from '../../api.js'
import usePolling from './usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

export default function LiveStatsPanel({ strategy }) {
  const fetcher = useMemo(() => () => api.metrics(strategy), [strategy])
  const { data: m } = usePolling(fetcher, 10000)
  const pnl = Number(m?.total_pnl || 0)
  return (
    <Card>
      <CardHeader><CardTitle>Live stats</CardTitle></CardHeader>
      <CardContent className="space-y-1 text-sm">
        <div className="flex justify-between"><span className="text-muted-foreground">Trades</span><span className="font-mono">{m?.n_trades ?? 0}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Win rate</span><span className="font-mono">{((Number(m?.win_rate || 0)) * 100).toFixed(1)}%</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Realized P&amp;L</span>
          <span className={`font-mono ${pnl >= 0 ? 'text-up' : 'text-down'}`}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Sharpe</span><span className="font-mono">{Number(m?.sharpe || 0).toFixed(2)}</span></div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 5: `components/detail/RecentTradesPanel.jsx` (per-strategy journal)**

```jsx
import { useMemo } from 'react'
import { api } from '../../api.js'
import usePolling from './usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

export default function RecentTradesPanel({ strategy }) {
  const fetcher = useMemo(() => () => api.journal(strategy), [strategy])
  const { data: trades } = usePolling(fetcher, 10000)
  const list = trades || []
  return (
    <Card>
      <CardHeader><CardTitle>Recent trades</CardTitle></CardHeader>
      <CardContent>
        {list.length === 0 ? <div className="text-sm text-muted-foreground">No closed trades yet.</div> : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted-foreground">
              <th className="font-medium">Time</th><th className="font-medium">P&amp;L</th><th className="font-medium">Result</th><th className="font-medium">Reason</th>
            </tr></thead>
            <tbody>
              {list.map((t, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="py-1 font-mono text-xs">{(t.exit_ts || '').replace('T', ' ').slice(0, 16)}</td>
                  <td className={`font-mono ${t.pnl >= 0 ? 'text-up' : 'text-down'}`}>{t.pnl >= 0 ? '+' : ''}{Number(t.pnl).toFixed(2)}</td>
                  <td>{t.pnl >= 0 ? 'WIN' : 'LOSS'}</td>
                  <td className="text-muted-foreground">{t.exit_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 6: `components/detail/JournalFeedPanel.jsx` (per-strategy trade reasons)**

```jsx
import { useMemo } from 'react'
import { api } from '../../api.js'
import usePolling from './usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

export default function JournalFeedPanel({ strategy }) {
  const fetcher = useMemo(() => () => api.journal(strategy), [strategy])
  const { data: trades } = usePolling(fetcher, 10000)
  const list = (trades || []).slice().sort((a, b) => (a.exit_ts < b.exit_ts ? 1 : -1))
  return (
    <Card>
      <CardHeader><CardTitle>Decision journal</CardTitle></CardHeader>
      <CardContent>
        <div className="max-h-72 space-y-1 overflow-y-auto">
          {list.length === 0 ? <div className="text-sm text-muted-foreground">No events yet.</div> : list.map((t, i) => (
            <div key={i} className="border-b border-border py-1 text-sm">
              <span className="text-muted-foreground">{(t.exit_ts || '').replace('T', ' ').slice(0, 16)} </span>
              <b>{t.exit_reason}</b> — {t.pnl >= 0 ? '+' : ''}{Number(t.pnl).toFixed(2)}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 7: `components/detail/BacktestComparisonPanel.jsx` (BTC/USD only, else note)**

```jsx
import { api } from '../../api.js'
import usePolling from './usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

function Stat({ title, m }) {
  if (!m) return <div className="flex-1 rounded-md border border-border p-3"><div className="text-xs text-muted-foreground">{title}</div><div>Loading…</div></div>
  const pnl = Number(m.total_pnl || 0)
  return (
    <div className="flex-1 rounded-md border border-border p-3">
      <div className="mb-1 text-xs text-muted-foreground">{title}</div>
      <div className="text-sm">Win rate <b>{(Number(m.win_rate || 0) * 100).toFixed(1)}%</b></div>
      <div className="text-sm">P&amp;L <b className={pnl >= 0 ? 'text-up' : 'text-down'}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</b></div>
      <div className="text-sm">Sharpe <b>{Number(m.sharpe || 0).toFixed(2)}</b></div>
      <div className="text-sm">Trades <b>{m.n_trades ?? 0}</b></div>
    </div>
  )
}

export default function BacktestComparisonPanel({ symbol }) {
  const supported = symbol === 'BTC/USD'
  const ema = usePolling(supported ? api.auto.backtestEma : async () => null, 60000)
  const kronos = usePolling(supported ? api.auto.backtestKronos : async () => null, 60000)
  return (
    <Card>
      <CardHeader><CardTitle>Backtest: EMA vs Kronos</CardTitle></CardHeader>
      <CardContent>
        {!supported ? (
          <div className="text-sm text-muted-foreground">Backtest is single-symbol (BTC/USD) only.</div>
        ) : (
          <div className="flex flex-wrap gap-3">
            <Stat title="EMA momentum" m={ema.data} />
            <Stat title="Kronos forecast" m={kronos.data} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 8: Rewrite `pages/CoinDetail.jsx` (resolve symbol from state)**

```jsx
import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { api } from '../api.js'
import { Button } from '../components/ui/button.jsx'
import { Badge } from '../components/ui/badge.jsx'
import { cardStatus } from '../lib/derive.js'
import ChartPanel from '../components/detail/ChartPanel.jsx'
import CurrentPositionPanel from '../components/detail/CurrentPositionPanel.jsx'
import LiveStatsPanel from '../components/detail/LiveStatsPanel.jsx'
import RecentTradesPanel from '../components/detail/RecentTradesPanel.jsx'
import BacktestComparisonPanel from '../components/detail/BacktestComparisonPanel.jsx'
import JournalFeedPanel from '../components/detail/JournalFeedPanel.jsx'

export default function CoinDetail() {
  const { name } = useParams()
  const strategyName = decodeURIComponent(name)
  const nav = useNavigate()
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try { setState(await api.state()) } catch { /* keep last */ }
  }, [])
  useEffect(() => { refresh(); const id = setInterval(refresh, 3000); return () => clearInterval(id) }, [refresh])

  const strat = (state?.strategies || []).find((s) => s.name === strategyName)
  const symbol = strat?.symbol
  const status = strat ? cardStatus(strat) : 'armed'
  const hasPosition = !!strat?.position && status !== 'armed'

  const act = async (fn) => { setBusy(true); try { await fn(); await refresh() } catch (e) { alert(e.message) } finally { setBusy(false) } }
  const removeFromWatchlist = async () => {
    const w = await api.watchlist()
    await api.setWatchlist((w.symbols || []).filter((s) => s !== symbol))
    if (status !== 'armed') await api.disarm(strategyName)
    nav('/')
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-muted-foreground hover:text-foreground"><ArrowLeft className="h-5 w-5" /></Link>
        <h1 className="text-lg font-semibold">{symbol || strategyName}</h1>
        <Badge variant="outline">{status}</Badge>
        <div className="ml-auto flex gap-2">
          {status === 'armed'
            ? <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => api.arm(strategyName))}>arm</Button>
            : <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => api.disarm(strategyName))}>disarm</Button>}
          {hasPosition && <Button size="sm" variant="danger" disabled={busy} onClick={() => act(() => api.flattenStrategy(strategyName))}>flatten</Button>}
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(removeFromWatchlist)}>remove</Button>
        </div>
      </div>

      {!strat ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          Strategy “{strategyName}” is not currently armed.
        </div>
      ) : (
        <>
          <ChartPanel symbol={symbol} strategy={strategyName} />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <CurrentPositionPanel strategy={strat} />
            <LiveStatsPanel strategy={strategyName} />
          </div>
          <BacktestComparisonPanel symbol={symbol} />
          <RecentTradesPanel strategy={strategyName} />
          <JournalFeedPanel strategy={strategyName} />
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 9: Verify build**

Run: `cd frontend && npm run build`
Expected: green.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/detail frontend/src/pages/CoinDetail.jsx
git commit -m "feat(ui): per-symbol Coin Detail panels + page"
```

---

### Task 12: Settings page — broker / rebalance / advanced

**Files:**
- Create: `frontend/src/components/settings/BrokerConnectionPanel.jsx` (extract the broker form from the old `pages/Settings.jsx`)
- Create: `frontend/src/components/settings/AdvancedControls.jsx`
- Rewrite: `frontend/src/pages/Settings.jsx`
- Modify: `frontend/src/components/RebalancePanel.jsx` (only if it imports `./Hint.jsx`, which is deleted in Task 13 — see Step 4)
- Modify: `frontend/src/components/TokenGate.jsx` (remove its `Hint` import; `Hint` is deleted in Task 13)

**Interfaces:**
- Consumes: `api.listBrokers/testBroker/setBrokerCreds/setActiveBroker/reconnectBroker`, `api.control`, `api.portfolioSettings/setPortfolioSettings`, `api.strategies/setLiveEligible`; `Card*`, `Button`, `Input`, `Label`, `Badge`; `RebalancePanel`, `TokenGate`.
- Produces: the `#/settings` page with three sections (Broker / Rebalance / Advanced) + TokenGate.

- [ ] **Step 1: Implement `components/settings/BrokerConnectionPanel.jsx`**

This is the Task-0 broker form, restyled (logic copied 1:1 from the old `pages/Settings.jsx`):
```jsx
import { useEffect, useState } from 'react'
import { api } from '../../api.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'
import { Button } from '../ui/button.jsx'
import { Input } from '../ui/input.jsx'
import { Label } from '../ui/label.jsx'

export default function BrokerConnectionPanel() {
  const [data, setData] = useState(null)
  const [sel, setSel] = useState('')
  const [vals, setVals] = useState({})
  const [mode, setMode] = useState('paper')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const load = async () => { const d = await api.listBrokers(); setData(d); setSel((prev) => prev || d.active) }
  useEffect(() => { load().catch((e) => setErr(e.message)) }, [])
  useEffect(() => { setVals({}); setMsg(''); setErr('') }, [sel])

  if (!data) return <Card><CardContent className="p-4">Loading…</CardContent></Card>
  const broker = data.brokers.find((b) => b.id === sel) || data.brokers[0]
  const setField = (n, v) => setVals((s) => ({ ...s, [n]: v }))
  const valuesPayload = () => {
    const out = { ...vals }
    if (broker.modes.includes('paper'))
      out.base_url = mode === 'paper' ? 'https://paper-api.alpaca.markets' : 'https://api.alpaca.markets'
    return out
  }
  const doTest = async () => { setErr(''); setMsg(''); try { const r = await api.testBroker(broker.id, valuesPayload(), mode); r.ok ? setMsg(`Test OK — ${r.detail}`) : setErr(`Test failed — ${r.detail}`) } catch (e) { setErr(e.message) } }
  const doSave = async () => { setErr(''); setMsg(''); try { await api.setBrokerCreds(broker.id, valuesPayload()); if (data.active !== broker.id) await api.setActiveBroker(broker.id); setMsg('Saved'); setVals({}); load() } catch (e) { setErr(e.message) } }
  const doReconnect = async () => { setErr(''); setMsg(''); try { const r = await api.reconnectBroker(); r.ok ? setMsg(`Reconnected — ${r.detail}`) : setErr(`Reconnect failed — ${r.detail}`) } catch (e) { setErr(e.message) } }

  return (
    <Card>
      <CardHeader><CardTitle>Broker connection</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {err && <div className="rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}
        {msg && <div className="rounded-md bg-up/15 px-3 py-2 text-sm text-up">{msg}</div>}
        <div className="space-y-1">
          <Label>Broker</Label>
          <select value={sel} onChange={(e) => setSel(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
            {data.brokers.map((b) => (
              <option key={b.id} value={b.id}>
                {b.label}{b.id === data.active ? ' (active)' : ''}{b.configured ? ' ✓' : ''}
              </option>
            ))}
          </select>
        </div>
        {broker.fields.map((f) => (
          <div key={f.name} className="space-y-1">
            <Label>{f.label}
              {broker.status.fields[f.name]?.set && !f.secret && <span className="ml-1 text-muted-foreground">(current: {broker.status.fields[f.name].value})</span>}
              {broker.status.fields[f.name]?.set && f.secret && <span className="ml-1 text-up">(set)</span>}
            </Label>
            <Input type={f.secret ? 'password' : 'text'} value={vals[f.name] || ''}
              placeholder={f.secret ? '••••••••' : ''} onChange={(e) => setField(f.name, e.target.value)} />
          </div>
        ))}
        {broker.modes.includes('paper') && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={mode === 'paper'} onChange={(e) => setMode(e.target.checked ? 'paper' : 'live')} />
            Paper endpoint
          </label>
        )}
        <div className="flex gap-2 pt-1">
          <Button size="sm" variant="outline" onClick={doTest}>Test connection</Button>
          <Button size="sm" onClick={doSave}>Save credentials</Button>
          <Button size="sm" variant="outline" onClick={doReconnect}>Reconnect bot</Button>
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Implement `components/settings/AdvancedControls.jsx`**

```jsx
import { useEffect, useState } from 'react'
import { api } from '../../api.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'
import { Button } from '../ui/button.jsx'

export default function AdvancedControls() {
  const [strategies, setStrategies] = useState([])
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = async () => { try { setStrategies(await api.strategies()) } catch (e) { setErr(e.message) } }
  useEffect(() => { load() }, [])

  const ctl = async (action) => { setErr(''); setMsg(''); try { await api.control(action); setMsg(`${action} ok`) } catch (e) { setErr(e.message) } }
  const toggleLive = async (s) => { setErr(''); try { await api.setLiveEligible(s.name, !s.live_eligible); await load() } catch (e) { setErr(e.message) } }

  return (
    <Card>
      <CardHeader><CardTitle>Advanced controls</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {err && <div className="rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}
        {msg && <div className="rounded-md bg-up/15 px-3 py-2 text-sm text-up">{msg}</div>}
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => ctl('pause')}>Pause</Button>
          <Button size="sm" variant="outline" onClick={() => ctl('resume')}>Resume</Button>
          <Button size="sm" variant="danger" onClick={() => ctl('halt')}>Halt (kill switch)</Button>
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">Live eligibility</div>
          {strategies.length === 0 ? <div className="text-sm text-muted-foreground">No strategies.</div> : (
            <div className="space-y-1">
              {strategies.map((s) => (
                <div key={s.name} className="flex items-center justify-between text-sm">
                  <span>{s.label || s.name} <span className="text-muted-foreground">({s.symbol})</span></span>
                  <Button size="sm" variant={s.live_eligible ? 'default' : 'outline'} onClick={() => toggleLive(s)}>
                    {s.live_eligible ? 'live-eligible ✓' : 'mark live-eligible'}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 3: Rewrite `pages/Settings.jsx`**

```jsx
import BrokerConnectionPanel from '../components/settings/BrokerConnectionPanel.jsx'
import AdvancedControls from '../components/settings/AdvancedControls.jsx'
import RebalancePanel from '../components/RebalancePanel.jsx'
import TokenGate from '../components/TokenGate.jsx'

export default function Settings() {
  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <h1 className="text-lg font-semibold">Settings</h1>
      <BrokerConnectionPanel />
      <RebalancePanel />
      <AdvancedControls />
      <TokenGate />
    </div>
  )
}
```

- [ ] **Step 4: Remove the `Hint` dependency from `TokenGate.jsx` and `RebalancePanel.jsx`**

`Hint.jsx` is deleted in Task 13, so any kept component that imports it must drop it now.
- In `components/TokenGate.jsx`: delete the line `import Hint from './Hint.jsx'` and remove the `<Hint ... />` element inside the `<h3>` (keep the heading text).
- Check `components/RebalancePanel.jsx`: run `grep -n "Hint" frontend/src/components/RebalancePanel.jsx`. If it imports/uses `Hint`, delete the import and each `<Hint .../>` usage. If there are no matches, leave the file unchanged.

- [ ] **Step 5: Verify build**

Run: `cd frontend && npm run build`
Expected: green. (At this point all three routes are fully functional; the only remaining imports of soon-to-be-deleted files are inside the orphaned old pages, which are no longer referenced by `App.jsx`.)

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/settings frontend/src/pages/Settings.jsx \
        frontend/src/components/TokenGate.jsx frontend/src/components/RebalancePanel.jsx
git commit -m "feat(ui): consolidated Settings (broker, rebalance, advanced controls)"
```

---

### Task 13: Remove manual-era remnants

**Files:**
- Delete pages: `Dashboard.jsx`, `Strategy.jsx`, `Discover.jsx`, `Brain.jsx`, `Health.jsx`, `Guide.jsx`, `AutoDashboard.jsx`
- Delete components: `ChartPanel.jsx`, `ControlBar.jsx`, `Hint.jsx`, `JournalTable.jsx`, `LifecycleBanner.jsx`, `MetricsPanel.jsx`, `PendingOrders.jsx`, `PortfolioBanner.jsx`, `PositionGrid.jsx`, `PositionPanel.jsx`, `PresetGallery.jsx`, `ReliabilityPanel.jsx`, `RiskPanel.jsx`, `SignalPanel.jsx`, `StatusBanner.jsx`, `StrategyBuilder.jsx`, `StrategyCard.jsx`, `StrategyManager.jsx`
- Delete dir: `components/AutoDash/` (panels superseded by `components/detail/`)
- Delete: `frontend/src/theme.css`, `frontend/src/guide.md`

**Interfaces:** none produced — this is pure removal. Nothing in `App.jsx`, the three pages, or the kept components imports any deleted file (verified in Step 2).

- [ ] **Step 1: Delete the files**

```bash
cd frontend/src
rm -f pages/Dashboard.jsx pages/Strategy.jsx pages/Discover.jsx pages/Brain.jsx \
      pages/Health.jsx pages/Guide.jsx pages/AutoDashboard.jsx
rm -f components/ChartPanel.jsx components/ControlBar.jsx components/Hint.jsx \
      components/JournalTable.jsx components/LifecycleBanner.jsx components/MetricsPanel.jsx \
      components/PendingOrders.jsx components/PortfolioBanner.jsx components/PositionGrid.jsx \
      components/PositionPanel.jsx components/PresetGallery.jsx components/ReliabilityPanel.jsx \
      components/RiskPanel.jsx components/SignalPanel.jsx components/StatusBanner.jsx \
      components/StrategyBuilder.jsx components/StrategyCard.jsx components/StrategyManager.jsx
rm -rf components/AutoDash
rm -f theme.css guide.md
cd ../..
```

- [ ] **Step 2: Verify no dangling imports remain**

Run:
```bash
cd frontend && grep -rEn "AutoDash|theme\.css|guide\.md|/Hint|/ControlBar|/PortfolioBanner|/Dashboard|/Strategy|/Discover|/Brain|/Health|/Guide|/PositionGrid|/PositionPanel|/JournalTable|/MetricsPanel|/PendingOrders|/PresetGallery|/ReliabilityPanel|/RiskPanel|/SignalPanel|/StatusBanner|/StrategyBuilder|/StrategyCard|/StrategyManager|/LifecycleBanner|AutoDashboard" src/ || echo "CLEAN"
```
Expected: `CLEAN` (no remaining references to any deleted module).

- [ ] **Step 3: Verify build**

Run: `cd frontend && npm run build`
Expected: green, smaller bundle (no `marked`, no manual pages).

- [ ] **Step 4: Commit**

```bash
git add -A frontend/src
git commit -m "chore(ui): remove manual-era pages, components, theme.css, guide.md"
```
(`-A frontend/src` is scoped to the frontend source tree only — it stages the deletions without touching the repo's unrelated uncommitted work elsewhere.)

---

### Task 14: Playwright smoke + backend gate + Docker rollout

**Files:**
- Create: `frontend/tests/redesign-smoke.spec.js` (or `docs/` script — see Step 1; uses the repo's existing Playwright MCP/runner pattern)
- Produce: `docs/redesign-smoke.png` (screenshot artifact)

**Interfaces:** none — verification + deployment task.

- [ ] **Step 1: Backend gate is untouched and green**

Run: `.venv/bin/python -m pytest -q`
Expected: `659 passed, 6 skipped` (the redesign touched no Python). If anything fails, stop — the change leaked outside the frontend.

- [ ] **Step 2: Frontend build + unit tests green**

Run: `cd frontend && npm run build && npm run test`
Expected: build green; `derive.test.js` passes.

- [ ] **Step 3: Docker rebuild + restart (standing policy)**

Run:
```bash
docker compose build swingbot && docker compose up -d swingbot
```
(If this host's daemon lacks the `nvidia` runtime, use the existing `runtime: runc` override as prior sessions did.) Wait for the container to report healthy.

- [ ] **Step 4: Playwright smoke on `:8000`**

Using the repo's Playwright tooling (the same approach as `docs/autodash-smoke.png`), drive `http://localhost:8000/#/` and assert the spec §13 checks:
1. Status strip renders (loop state word RUNNING/PAUSED/STOPPED + a mode badge PAPER/LIVE visible).
2. Coins grid shows ≥1 card **or** the empty-state "Add coin" affordance is present.
3. The Start/Stop button toggles (click it, confirm the label flips; click back to restore prior state).
4. "Add coin" opens the dialog (a dialog with a symbol list or "all symbols added" appears).
5. Clicking a coin card navigates to `#/coin/<name>` and the detail chart heading renders.
6. `#/settings` renders the Broker connection panel heading.
Capture a full-page screenshot of `#/` to `docs/redesign-smoke.png`.

- [ ] **Step 5: Live-verify the broker-recovery path is reachable**

Confirm (read-only — do **not** submit a probe PUT that overwrites creds, per the standing live-verify rule) that when the broker is unauthorized the amber "Broker not connected — fix in Settings" banner is present on `#/`, and that `#/settings` shows the broker form. (Today's stale paper key yields the 401; this is the exact recovery surface.)

- [ ] **Step 6: Commit the smoke artifacts**

```bash
git add frontend/tests/redesign-smoke.spec.js docs/redesign-smoke.png
git commit -m "test(ui): redesign Playwright smoke + screenshot artifact"
```

- [ ] **Step 7: Update the roadmap status**

Append a "✅ AUTONOMOUS-FIRST UI REDESIGN — COMPLETE" block to `docs/ROADMAP_STATUS.md` (branch/commit, gate numbers, smoke result, and the new 3-route IA), then commit:
```bash
git add docs/ROADMAP_STATUS.md
git commit -m "docs: record autonomous-first UI redesign completion"
```

---

## Self-Review

**Spec coverage (§ by §):**
- §4 IA (3 routes, HashRouter, token bootstrap, TokenGate) → Task 4. ✅
- §5.1 Status strip → Task 5 (loop state, mode, equity/PnL, Start/Stop toggle, health dots, broker banner). ✅
- §5.2 Coins grid + card actions + Add coin + click-through → Tasks 6, 7. ✅
- §5.3 Rebalance strip → Task 8. ✅
- §5.4 Live decision journal + reliability → Task 9. ✅
- §6 Coin Detail (6 panels per-symbol, per-coin controls incl. remove-from-watchlist) → Task 11. ✅
- §7 Settings (broker / rebalance / advanced + token gate) → Task 12. ✅
- §8 Removed inventory → Task 13 (every listed page/component deleted; AutoDash superseded). ✅
- §9 Tech stack (Tailwind, shadcn, react-router, drop `marked`/`theme.css`) → Tasks 1, 2, 13. ✅
- §10 Backtest single-symbol call-out → Task 11 Step 7 (BTC/USD gated + note). ✅
- §11 File structure → realized across Tasks 1–13. ✅
- §12 Visual direction → Task 1 tokens. ✅
- §13 Testing (build + Playwright smoke + backend 659/6) → Tasks 3, 14. ✅
- §14 Rollout (Docker rebuild + live-verify) → Task 14. ✅

**Placeholder scan:** no "TBD/handle edge cases/similar to Task N"; every code step shows complete code; design tokens are concrete hex/HSL, not "finalize later".

**Type/name consistency:** `lib/derive.js` signatures (`loopState`, `cardStatus`, `availableToAdd`, `lastDecision`, `brokerUnauthorized`, `reliabilityPct`, `dayPnl`, `dayPnlPct`, `equityOf`, `modeBadge`) are defined in Task 3 and consumed with the same names/arities in Tasks 5, 6, 9, 11. Component props (`StatusStrip{state,health,onChange}`, `CoinsGrid{state,health,onChange,onAdd}`, `CoinCard{strategy,health,onChange}`, `AddCoinDialog{open,onOpenChange,onAdded}`, detail panels `{symbol|strategy}`) match between producer and consumer tasks. Route key is `:name` (strategy name) everywhere (cards link `encodeURIComponent(strategy.name)`, CoinDetail `decodeURIComponent(name)`).

**Gap fixes folded in:** `usePolling` is copied into `components/detail/` (Task 11) so Coin Detail panels have no dependency on the deleted `AutoDash/` dir; `RebalanceStrip` uses a self-contained poll to avoid a cross-task hook-path hazard; `TokenGate`/`RebalancePanel` shed their `Hint` import in Task 12 before `Hint` is deleted in Task 13.
