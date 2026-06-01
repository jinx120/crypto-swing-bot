# Phase 3 — Frontend Multi-Chart Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the single-strategy dashboard into a portfolio view — a portfolio summary banner plus a responsive grid of per-strategy cards (each with its own mini chart, signal, position, and controls) — and add arm/disarm + live-eligible + portfolio-settings UI. Fix the stale-ticker lag by making every chart key off an explicit symbol.

**Architecture:** New `/api/state` returns `{portfolio, strategies[]}`. `App` polls it and renders a `PortfolioBanner` + a grid of `StrategyCard`s keyed by symbol. `ChartPanel` gains a required `symbol` prop (no more server-active fallback) so switching strategies can't leave stale tickers. Per-card mini charts show candles + position lines, no trade markers (keeps many charts light); aggregate journal/metrics stay in portfolio-level panels.

**Tech Stack:** React 18, Vite, lightweight-charts v5. No JS test runner — verify with `npm run build` (must succeed) + the manual checks each task lists. Commands run from `frontend/`.

**Reference:** Design spec `docs/superpowers/specs/2026-05-31-multi-asset-concurrent-trading-design.md` §8. Depends on Phase 2 (run the backend with `swingbot-web` to manually verify).

---

### Task 1: API client — portfolio + arming methods

**Files:**
- Modify: `frontend/src/api.js`

- [ ] **Step 1: Add the new methods**

In `frontend/src/api.js`, replace the `export const api = { ... }` object with this
superset (existing methods unchanged; new ones appended):

```jsx
export const api = {
  state: () => req('GET', '/api/state'),
  journal: (strategy) => req('GET', strategy ? `/api/journal?strategy=${encodeURIComponent(strategy)}` : '/api/journal'),
  metrics: (strategy) => req('GET', strategy ? `/api/metrics?strategy=${encodeURIComponent(strategy)}` : '/api/metrics'),
  listProfiles: () => req('GET', '/api/profiles'),
  getProfile: (name) => req('GET', `/api/profiles/${name}`),
  saveProfile: (name, profile) => req('POST', '/api/profiles', { name, profile }),
  deleteProfile: (name) => req('DELETE', `/api/profiles/${name}`),
  credStatus: () => req('GET', '/api/credentials'),
  setCreds: (key_id, secret_key, base_url) =>
    req('PUT', '/api/credentials', { key_id, secret_key, base_url }),
  control: (action, body) => req('POST', `/api/control/${action}`, body),
  flattenStrategy: (name) => req('POST', `/api/control/${encodeURIComponent(name)}/flatten`),
  candles: (symbol, timeframe, limit = 500) => {
    const q = new URLSearchParams()
    if (symbol) q.set('symbol', symbol)
    if (timeframe) q.set('timeframe', timeframe)
    q.set('limit', String(limit))
    return req('GET', `/api/candles?${q.toString()}`)
  },
  presets: () => req('GET', '/api/presets'),
  buildStrategy: (body) => req('POST', '/api/strategy/build', body),
  backtestProfile: (profile) => req('POST', '/api/strategy/backtest', { profile }),
  // --- portfolio / arming ---
  strategies: () => req('GET', '/api/strategies'),
  arm: (name) => req('POST', '/api/strategies/arm', { name }),
  disarm: (name) => req('POST', '/api/strategies/disarm', { name }),
  setLiveEligible: (name, eligible) => req('POST', '/api/strategies/live-eligible', { name, eligible }),
  portfolioSettings: () => req('GET', '/api/portfolio/settings'),
  setPortfolioSettings: (patch) => req('PUT', '/api/portfolio/settings', patch),
}
```

(Note: `activeProfile`/`setActive` are removed — the armed model replaces them. Task 5
updates the one caller in `Strategy.jsx`.)

- [ ] **Step 2: Build**

Run: `npm run build`
Expected: succeeds (Strategy.jsx still references `api.activeProfile`; that breaks the build
until Task 5. If you are executing strictly task-by-task, run the build at the end of Task 5
instead and commit this step without building.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat(ui): API client methods for portfolio state, arming, live-eligible, settings"
```

---

### Task 2: ChartPanel takes a required symbol; add mini mode

Remove the server-active fallback (`api.candles()` with no args) so the chart always renders
the symbol it's told to — this is the stale-ticker fix. Add a `mini` prop for compact cards.

**Files:**
- Modify: `frontend/src/components/ChartPanel.jsx`

- [ ] **Step 1: Change the component signature and defaults**

In `frontend/src/components/ChartPanel.jsx`, change the function signature:

```jsx
export default function ChartPanel({ symbol, timeframe, trades = [], position, mini = false }) {
```

In `DEFAULT_CFG`, when `mini`, markers/indicators should default off. Replace the
`const [cfg, setCfg] = useState(loadCfg)` line with:

```jsx
  const [cfg, setCfg] = useState(() => {
    const base = loadCfg()
    return mini ? { ...base, markers: false, sma: false, ema: false, volume: false } : base
  })
```

- [ ] **Step 2: Make the fetch use the explicit symbol/timeframe**

Replace the entire fetch `useEffect` (`// ── fetch candles ...`) `load` function body and
deps. The new effect:

```jsx
  // ── fetch candles for the explicit symbol/timeframe, poll every 10s ──
  useEffect(() => {
    if (!symbol) { setCount(0); return }
    let alive = true
    const tf = cfg.timeframe || timeframe || '15m'
    const load = async () => {
      try {
        const r = await api.candles(symbol, tf)
        if (!alive) return
        setErr('')
        setMeta({ symbol: r.symbol, timeframe: r.timeframe })
        const candles = sanitize(r.candles)
        dataRef.current = candles
        setCount(candles.length)
        candleRef.current?.setData(candles.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })))
        volRef.current?.setData(candles.map(c => ({ time: c.time, value: Number.isFinite(c.volume) ? c.volume : 0,
          color: c.close >= c.open ? 'rgba(54,209,122,0.4)' : 'rgba(255,84,112,0.4)' })))
        applyIndicators()
        if (candles.length && !fittedRef.current) { chartRef.current?.timeScale().fitContent(); fittedRef.current = true }
      } catch (e) { if (alive) setErr(e.message) }
    }
    load()
    const id = setInterval(load, 10000)
    return () => { alive = false; clearInterval(id) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfg.timeframe, symbol, timeframe])
```

(The `sanitize` helper was added in Phase 0; if executing phases out of order, add it now
from the Phase 0 plan Task 2 Step 1.)

- [ ] **Step 3: Use the symbol prop for the label and reset fit on symbol change**

Replace `const label = meta.symbol || symbol || '—'` with:

```jsx
  const label = symbol || meta.symbol || '—'
```

Add a `useEffect` (just below the `activeTf` line) that re-fits when the symbol changes:

```jsx
  useEffect(() => { fittedRef.current = false }, [symbol])
```

- [ ] **Step 4: In mini mode, render a compact panel (hide the toolbar)**

Wrap the timeframe toolbar so it only shows when not mini. Replace the `<div className="chart-tfs"> ... </div>` block with:

```jsx
        {!mini && <div className="chart-tfs">
          {TIMEFRAMES.map(tf => (
            <button key={tf} className={`tf ${activeTf === tf ? 'active' : ''}`}
              onClick={() => set({ timeframe: tf })}>{tf}</button>
          ))}
          <button className={`tf gear ${showCfg ? 'active' : ''}`} title="Chart settings"
            onClick={() => setShowCfg(s => !s)} aria-label="Chart settings">⚙</button>
        </div>}
```

And give the box a mini class. Replace `<div className="chart-box" ref={boxRef} />` with:

```jsx
      <div className={`chart-box ${mini ? 'mini' : ''}`} ref={boxRef} />
```

- [ ] **Step 5: Add the mini chart CSS**

In `frontend/src/theme.css`, after the `.chart-panel .chart-box{...}` rule, add:

```css
.chart-panel .chart-box.mini{height:200px}
```

- [ ] **Step 6: Build**

Run: `npm run build`
Expected: succeeds (same Strategy.jsx caveat as Task 1 — defer the build to Task 5 if going
strictly in order).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/ChartPanel.jsx frontend/src/theme.css
git commit -m "feat(ui): ChartPanel requires explicit symbol (stale-ticker fix) + mini mode"
```

---

### Task 3: PortfolioBanner + StrategyCard components

**Files:**
- Create: `frontend/src/components/PortfolioBanner.jsx`
- Create: `frontend/src/components/StrategyCard.jsx`

- [ ] **Step 1: Create the portfolio banner**

Create `frontend/src/components/PortfolioBanner.jsx`:

```jsx
import Hint from './Hint.jsx'

export default function PortfolioBanner({ portfolio }){
  const p = portfolio || {}
  const halted = p.kill_switch?.active
  const pnl = p.day_pnl ?? 0
  const f = (x, d = 2) => (typeof x === 'number' ? x.toFixed(d) : '—')
  return (
    <div className={`banner ${halted ? 'halted' : ''}`}>
      <span>Mode: <b>{(p.mode || 'paper').toUpperCase()}</b>
        <Hint pos="below" text="Whole-portfolio money mode. PAPER = simulated; LIVE = real money (gated)." />
      </span>
      <span>Equity: <b>{f(p.equity)}</b></span>
      <span>Deployed: <b>{f(p.deployed)}</b> ({f((p.deployed_frac || 0) * 100, 0)}%)
        <Hint pos="below" text="Total value in open positions across all strategies, and as a % of equity. The portfolio cap blocks new entries past your max." />
      </span>
      <span>Open: <b>{p.open_positions ?? 0}</b>
        <Hint pos="below" text="How many strategies hold a position right now, across the whole portfolio." />
      </span>
      <span>Day P&L: <b className={pnl >= 0 ? 'pos' : 'neg'}>{pnl >= 0 ? '+' : ''}{f(pnl)}</b>
        <Hint pos="below" text="Aggregate realized P&L across all strategies today. Past the portfolio daily-loss limit, the portfolio kill switch trips." />
      </span>
      {halted && <span className="neg">⛔ PORTFOLIO KILL SWITCH: {p.kill_switch.reason}</span>}
    </div>
  )
}
```

- [ ] **Step 2: Create the per-strategy card**

Create `frontend/src/components/StrategyCard.jsx`:

```jsx
import { useState } from 'react'
import { api } from '../api.js'
import ChartPanel from './ChartPanel.jsx'
import SignalPanel from './SignalPanel.jsx'
import PositionPanel from './PositionPanel.jsx'
import Hint from './Hint.jsx'

export default function StrategyCard({ strategy, mode, onChange }){
  const [err, setErr] = useState('')
  const s = strategy || {}
  const run = async (fn, confirmMsg) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return
    setErr('')
    try { await fn(); onChange?.() } catch (e) { setErr(e.message) }
  }
  const paperOnly = mode === 'live' && !s.live_eligible
  return (
    <div className="panel full strategy-card">
      <h3>{s.name} — {s.symbol}
        <Hint text="One armed strategy trading one symbol. Its signal, position, and controls are scoped to this card." />
        {paperOnly && <span className="chip warn" title="Armed but not live-eligible — manages open trades but opens none in LIVE mode">paper-only</span>}
      </h3>
      {err && <div className="err">{err}</div>}
      <ChartPanel symbol={s.symbol} mini position={s.position} />
      <div className="card-cols">
        <SignalPanel signal={s.snapshot} symbol={s.symbol} />
        <PositionPanel position={s.position} />
      </div>
      <div className="card-actions">
        <button className="act danger"
          onClick={() => run(() => api.flattenStrategy(s.name), `Flatten ${s.symbol} now?`)}>Flatten</button>
        <button className="act danger"
          onClick={() => run(() => api.disarm(s.name), `Disarm ${s.name}? Its open position is flattened first.`)}>Disarm</button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Add card CSS**

In `frontend/src/theme.css`, after the `tr.rec td{...}` rule (end of presets block), add:

```css
/* ── Per-strategy cards ── */
.strategy-card .card-cols{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
.strategy-card .card-actions{display:flex;gap:8px;margin-top:12px}
.chip.warn{background:linear-gradient(180deg,rgba(245,166,35,.9),rgba(245,166,35,.6));
  border:1px solid rgba(245,166,35,.4);margin-left:8px}
@media (max-width:820px){ .strategy-card .card-cols{grid-template-columns:1fr} }
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PortfolioBanner.jsx frontend/src/components/StrategyCard.jsx frontend/src/theme.css
git commit -m "feat(ui): PortfolioBanner + StrategyCard components"
```

---

### Task 4: Dashboard renders the portfolio grid

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

- [ ] **Step 1: Rewrite Dashboard**

Replace the entire contents of `frontend/src/pages/Dashboard.jsx` with:

```jsx
import StrategyCard from '../components/StrategyCard.jsx'
import JournalTable from '../components/JournalTable.jsx'
import MetricsPanel from '../components/MetricsPanel.jsx'

export default function Dashboard({ state, trades, metrics, onChange }){
  const strategies = state?.strategies || []
  const mode = state?.portfolio?.mode
  return (
    <div className="wrap">
      {strategies.length === 0 && (
        <div className="panel full"><h3>No strategies armed</h3>
          <div>Arm one or more strategies on the <b>Strategy</b> tab to start trading them concurrently.</div>
        </div>
      )}
      {strategies.map(s => (
        <StrategyCard key={s.symbol || s.name} strategy={s} mode={mode} onChange={onChange} />
      ))}
      <MetricsPanel metrics={metrics} />
      <JournalTable trades={trades} />
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Dashboard.jsx
git commit -m "feat(ui): Dashboard renders portfolio banner grid of strategy cards"
```

---

### Task 5: Strategy page — arm/disarm + live-eligible + portfolio settings

**Files:**
- Create: `frontend/src/components/StrategyManager.jsx`
- Modify: `frontend/src/pages/Strategy.jsx`

- [ ] **Step 1: Create the manager component**

Create `frontend/src/components/StrategyManager.jsx`:

```jsx
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import Hint from './Hint.jsx'

export default function StrategyManager({ refreshKey }){
  const [rows, setRows] = useState([])
  const [settings, setSettings] = useState(null)
  const [err, setErr] = useState('')
  const load = async () => {
    try { setRows(await api.strategies()); setSettings(await api.portfolioSettings()); setErr('') }
    catch (e) { setErr(e.message) }
  }
  useEffect(() => { load() }, [refreshKey])
  const act = async (fn) => { setErr(''); try { await fn(); load() } catch (e) { setErr(e.message) } }
  const setS = (k) => (v) => setSettings(s => ({ ...s, [k]: v }))
  const saveSettings = () => act(() => api.setPortfolioSettings({
    max_concurrent: Number(settings.max_concurrent),
    max_total_deployed_frac: Number(settings.max_total_deployed_frac),
    portfolio_daily_loss_limit_pct: Number(settings.portfolio_daily_loss_limit_pct),
  }))
  return (
    <div className="panel full">
      <h3>Armed strategies
        <Hint text="Which strategies trade concurrently. Arm several (one per symbol). Live-eligible decides whether a strategy may open trades once the portfolio is in LIVE mode." />
      </h3>
      {err && <div className="err">{err}</div>}
      <table><thead><tr><th>Profile</th><th>Symbol</th><th>Armed</th><th>Live-eligible</th><th></th></tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.name}>
              <td>{r.name}</td><td>{r.symbol}</td>
              <td>{r.armed ? '✓' : '—'}</td>
              <td>{r.armed
                ? <input type="checkbox" style={{ width: 'auto' }} checked={r.live_eligible}
                    onChange={e => act(() => api.setLiveEligible(r.name, e.target.checked))} />
                : '—'}</td>
              <td>{r.armed
                ? <button className="act" onClick={() => act(() => api.disarm(r.name))}>Disarm</button>
                : <button className="act" onClick={() => act(() => api.arm(r.name))}>Arm</button>}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan="5">No profiles yet — create one below.</td></tr>}
        </tbody></table>

      {settings && <>
        <h3 style={{ marginTop: 16 }}>Portfolio caps
          <Hint text="Shared-pool safety limits applied across all strategies at once." />
        </h3>
        <label>Max concurrent positions<Hint text="Most positions open across the whole portfolio at once. A diversification/exposure cap, separate from how many you arm." /></label>
        <input type="number" value={settings.max_concurrent} onChange={e => setS('max_concurrent')(e.target.value)} />
        <label>Max total deployed (fraction of equity)<Hint text="Cap on the summed value of all open positions, e.g. 0.8 = 80% of equity. New entries that would breach it are skipped." /></label>
        <input type="number" step="0.01" value={settings.max_total_deployed_frac} onChange={e => setS('max_total_deployed_frac')(e.target.value)} />
        <label>Portfolio daily-loss kill switch<Hint text="If the whole portfolio's realized loss for the day reaches this fraction of equity, the portfolio kill switch trips and blocks all new entries." /></label>
        <input type="number" step="0.01" value={settings.portfolio_daily_loss_limit_pct} onChange={e => setS('portfolio_daily_loss_limit_pct')(e.target.value)} />
        <button className="act" style={{ marginTop: 12 }} onClick={saveSettings}>Save portfolio caps</button>
      </>}
    </div>
  )
}
```

- [ ] **Step 2: Mount it on the Strategy page and drop the old active-pointer code**

In `frontend/src/pages/Strategy.jsx`:

(a) Add the import near the top (after the `StrategyBuilder` import):

```jsx
import StrategyManager from '../components/StrategyManager.jsx'
```

(b) Replace the `load` function and the `active` state. Change:

```jsx
  const [names, setNames] = useState([]); const [active, setActive] = useState(null)
```

to:

```jsx
  const [names, setNames] = useState([]); const [refreshKey, setRefreshKey] = useState(0)
```

Change:

```jsx
  const load = async () => { setNames(await api.listProfiles()); setActive((await api.activeProfile()).name) }
```

to:

```jsx
  const load = async () => { setNames(await api.listProfiles()); setRefreshKey(k => k + 1) }
```

(c) In the "Profiles" panel, replace the per-row Set-active button block. Change:

```jsx
        {names.map(n => (
          <div className="row" key={n}>
            <span>{n} {active === n && <span className="chip">active</span>}</span>
            <span>
              <button className="act" onClick={() => edit(n)}>Edit</button>
              <button className="act" onClick={() => api.setActive(n).then(load).catch(e => setErr(e.message))}>Set active</button>
              <button className="act danger" onClick={() => api.deleteProfile(n).then(load)}>Delete</button>
            </span>
          </div>
        ))}
```

to:

```jsx
        {names.map(n => (
          <div className="row" key={n}>
            <span>{n}</span>
            <span>
              <button className="act" onClick={() => edit(n)}>Edit</button>
              <button className="act danger" onClick={() => api.deleteProfile(n).then(load)}>Delete</button>
            </span>
          </div>
        ))}
```

(d) Add `<StrategyManager refreshKey={refreshKey} />` as the first child inside the
returned `<div className="wrap">`, before `<PresetGallery .../>`:

```jsx
    <div className="wrap">
      <StrategyManager refreshKey={refreshKey} />
      <PresetGallery symbol={f.symbol} onUse={applyProfile} />
```

- [ ] **Step 3: Build**

Run: `npm run build`
Expected: succeeds (all `api.activeProfile`/`api.setActive` references are now gone).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/StrategyManager.jsx frontend/src/pages/Strategy.jsx
git commit -m "feat(ui): StrategyManager — arm/disarm, live-eligible, portfolio caps; drop active pointer"
```

---

### Task 6: App wires the new state shape + portfolio banner

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Update App**

In `frontend/src/App.jsx`:

(a) Replace the `StatusBanner` import with the portfolio banner:

```jsx
import PortfolioBanner from './components/PortfolioBanner.jsx'
```

(remove the `import StatusBanner from './components/StatusBanner.jsx'` line.)

(b) The `refresh` callback already fetches `state`, `journal`, `metrics` — keep it, but drop
the per-tick journal/metrics frequency by polling them less often. Replace the polling
`useEffect` with:

```jsx
  useEffect(()=>{
    refresh()
    const fast = setInterval(async()=>{
      try { const s = await api.state(); setState(s); setErr(''); setUnreachable(false) }
      catch(e){ setErr(e.message); if (e.network) setUnreachable(true) }
    }, 3000)
    const slow = setInterval(async()=>{
      try { setTrades(await api.journal()); setMetrics(await api.metrics()) } catch {}
    }, 10000)
    return ()=>{ clearInterval(fast); clearInterval(slow) }
  }, [refresh])
```

(c) Replace the `const live = state?.mode === 'live'` line with:

```jsx
  const live = state?.portfolio?.mode === 'live'
```

(d) Replace the mode badge text source in the nav. Change:

```jsx
        <span className={`mode ${live?'live':''}`}>{(state?.mode || 'paper').toUpperCase()}
```

to:

```jsx
        <span className={`mode ${live?'live':''}`}>{(state?.portfolio?.mode || 'paper').toUpperCase()}
```

(e) Replace the dashboard banner + body. Change:

```jsx
      {tab==='dashboard' && <StatusBanner state={state} />}
      {err && <div className="err" style={{padding:'8px 20px'}}>{err}</div>}
      {tab==='dashboard' && <>
        <Dashboard state={state} trades={trades} metrics={metrics} />
        <div className="wrap"><ControlBar state={state} onChange={refresh} /></div>
      </>}
```

to:

```jsx
      {tab==='dashboard' && <PortfolioBanner portfolio={state?.portfolio} />}
      {err && !unreachable && <div className="err" style={{padding:'8px 20px'}}>{err}</div>}
      {tab==='dashboard' && <>
        <Dashboard state={state} trades={trades} metrics={metrics} onChange={refresh} />
        <div className="wrap"><ControlBar portfolio={state?.portfolio} onChange={refresh} /></div>
      </>}
```

- [ ] **Step 2: Update ControlBar to read the portfolio**

In `frontend/src/components/ControlBar.jsx`, change the signature and the two state reads.
Replace `export default function ControlBar({ state, onChange }){` with:

```jsx
export default function ControlBar({ portfolio, onChange }){
```

Replace:

```jsx
  const paused = state?.paused
  const running = state?.running
```

with:

```jsx
  const paused = portfolio?.paused
  const running = portfolio?.running
```

- [ ] **Step 3: Build and manually verify end-to-end**

Run: `npm run build`
Expected: succeeds.

Manual check (backend from Phase 2 running via `swingbot-web`, creds + ≥2 armed profiles):
- Dashboard shows the portfolio banner and one card per armed strategy, each with its own
  chart and signal.
- Arming/disarming on the Strategy tab adds/removes a card within a couple of seconds.
- Switching a profile's symbol and re-arming updates the card's ticker everywhere with no
  stale leftover (the stale-ticker bug is gone because each chart keys off its symbol).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.jsx frontend/src/components/ControlBar.jsx
git commit -m "feat(ui): App consumes portfolio state shape; PortfolioBanner + slower journal/metrics polling"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** §8 multi-chart grid (Tasks 3-4), arm/disarm + live-eligible UI (Task 5),
  portfolio banner (Tasks 3,6), reactivity/stale-ticker fix (Task 2 + keyed cards in Task 4),
  lighter polling (Task 6). The Phase-0 tooltip/null/unreachable fixes are assumed present.
- **Dead components:** `StatusBanner.jsx` is no longer imported (superseded by
  `PortfolioBanner`); `SignalPanel`/`PositionPanel` are reused inside `StrategyCard`. Leave
  `StatusBanner.jsx` in the tree (harmless) or delete it in a follow-up.
- **Per-card markers off by design:** mini charts skip trade markers to stay light and to
  avoid N per-strategy journal fetches; aggregate journal/metrics remain in the
  portfolio-level panels at the bottom of the dashboard.
- **`RiskPanel.jsx`** is no longer on the dashboard (its kill-switch/mode now live in the
  portfolio banner and per-card risk). Leave it for now.
