# Phase 3B — React Valhalla Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** A Valhalla-styled React single-page app that runs the whole bot from the browser — monitor live state, control the bot (halt/resume/flatten/mode), edit strategy profiles, and enter Alpaca credentials — all against the Phase 3A FastAPI backend. No JSON/.env editing.

**Architecture:** React 18 + Vite + plain CSS (mirrors `algo-research-agent/frontend`). A small `api.js` client wraps fetch, attaches the `X-Token` header (token stored in `localStorage`) on writes, and polls `GET /api/state` every 2s for live updates. Three tabs — **Dashboard**, **Strategy**, **Settings** — render against the backend. Dark navy Valhalla theme (status banner, score chips, dense tables, green/red numerics, red LIVE indicator).

**Verification approach (no unit-test runner):** each task is verified by `npm run build` (must compile clean) and, at the end, a Playwright render smoke against a running `swingbot-web`. This is deliberate — React view code is verified by building + rendering, not pytest.

**Tech Stack:** Node/npm, Vite 5, React 18, plain CSS. Lives in `crypto-swing-bot/frontend/`.

---

## File Structure
```
frontend/
  package.json            # react, react-dom, vite, @vitejs/plugin-react
  vite.config.js          # dev server :3000, proxy /api -> :8000
  index.html
  src/
    main.jsx
    App.jsx               # tab router + 2s state polling + token gate
    api.js                # fetch wrappers + token handling
    theme.css            # Valhalla dark theme
    components/
      StatusBanner.jsx     # RUNNING/HALTED, regime, day P&L, MODE (red if LIVE)
      SignalPanel.jsx      # per-signal value×weight=contribution, score vs threshold, regime verdict
      PositionPanel.jsx    # entry/now/size/stop/tp, or "Flat"
      RiskPanel.jsx        # equity, kill switch, consecutive losses, day P&L
      JournalTable.jsx     # dense trade table
      MetricsPanel.jsx     # expectancy, win rate, PF, max DD, n
      ControlBar.jsx       # HALT/reset/pause/resume/flatten/mode + confirms
      TokenGate.jsx        # one-time token entry (stored in localStorage)
    pages/
      Dashboard.jsx        # banner + signal + position + risk + journal + metrics
      Strategy.jsx         # list/create/edit/select profiles
      Settings.jsx         # Alpaca credentials form (masked) + token
```

---

## Task 1: Scaffold Vite app + Valhalla theme + API client

**Files:** create `frontend/` tree (package.json, vite.config.js, index.html, src/main.jsx, src/api.js, src/theme.css, a placeholder src/App.jsx)

- [ ] **Step 1: `frontend/package.json`**
```json
{
  "name": "swingbot-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": { "dev": "vite", "build": "vite build", "preview": "vite preview" },
  "dependencies": { "react": "^18.3.1", "react-dom": "^18.3.1" },
  "devDependencies": { "@vitejs/plugin-react": "^4.3.1", "vite": "^5.3.1" }
}
```

- [ ] **Step 2: `frontend/vite.config.js`**
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 3000, proxy: { '/api': 'http://localhost:8000' } },
})
```

- [ ] **Step 3: `frontend/index.html`**
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>SwingBot</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 4: `frontend/src/main.jsx`**
```jsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './theme.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode><App /></React.StrictMode>
)
```

- [ ] **Step 5: `frontend/src/api.js`**
```js
const TOKEN_KEY = 'swingbot_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY) || ''
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t)

async function req(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  if (method !== 'GET') headers['X-Token'] = getToken()
  const res = await fetch(path, {
    method, headers, body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || detail.reason || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  state: () => req('GET', '/api/state'),
  journal: () => req('GET', '/api/journal'),
  metrics: () => req('GET', '/api/metrics'),
  listProfiles: () => req('GET', '/api/profiles'),
  activeProfile: () => req('GET', '/api/profiles/active'),
  saveProfile: (name, profile) => req('POST', '/api/profiles', { name, profile }),
  setActive: (name) => req('POST', '/api/profiles/active', { name }),
  deleteProfile: (name) => req('DELETE', `/api/profiles/${name}`),
  credStatus: () => req('GET', '/api/credentials'),
  setCreds: (key_id, secret_key, base_url) =>
    req('PUT', '/api/credentials', { key_id, secret_key, base_url }),
  control: (action, body) => req('POST', `/api/control/${action}`, body),
}
```

- [ ] **Step 6: `frontend/src/theme.css`** (Valhalla dark)
```css
:root{
  --bg:#0f1623; --panel:#16202e; --panel2:#1c2838; --line:#243246;
  --text:#cdd6e3; --muted:#7c8aa0; --green:#36d17a; --red:#ff5470;
  --accent:#3b82f6; --chip:#1f6f43; --rs:#a855f7; --amber:#f5a623;
}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);
  font-family:ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif;font-size:14px}
.nav{display:flex;align-items:center;gap:18px;padding:12px 20px;background:#0c1320;border-bottom:1px solid var(--line)}
.nav .brand{font-weight:700;color:#fff;letter-spacing:.5px}
.nav button{background:none;border:none;color:var(--muted);cursor:pointer;font-size:14px;padding:6px 4px}
.nav button.active{color:#fff;border-bottom:2px solid var(--accent)}
.mode{margin-left:auto;font-weight:700;padding:4px 10px;border-radius:6px;background:#1f6f43;color:#fff}
.mode.live{background:var(--red)}
.banner{display:flex;gap:16px;align-items:center;padding:10px 20px;background:#123a26;border-bottom:1px solid var(--line)}
.banner.halted{background:#3a1620}
.wrap{padding:20px;display:grid;gap:16px;grid-template-columns:1fr 1fr}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.panel h3{margin:0 0 10px;font-size:12px;letter-spacing:.6px;color:var(--muted);text-transform:uppercase}
.full{grid-column:1 / -1}
.row{display:flex;justify-content:space-between;padding:3px 0}
.pos{color:var(--green)} .neg{color:var(--red)}
.chip{display:inline-block;padding:2px 8px;border-radius:5px;background:var(--chip);color:#fff;font-weight:700}
table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:600;font-size:12px}
button.act{background:var(--panel2);border:1px solid var(--line);color:var(--text);
  padding:8px 14px;border-radius:7px;cursor:pointer;margin-right:8px}
button.danger{border-color:var(--red);color:var(--red)}
input,select{background:#0c1320;border:1px solid var(--line);color:var(--text);
  padding:8px;border-radius:6px;width:100%}
label{display:block;color:var(--muted);font-size:12px;margin:10px 0 4px}
.err{color:var(--red);margin:8px 0}
```

- [ ] **Step 7: placeholder `frontend/src/App.jsx`** (replaced in later tasks)
```jsx
export default function App(){ return <div className="nav"><span className="brand">⚡ SwingBot</span></div> }
```

- [ ] **Step 8: install + build**
```bash
cd /home/redji/crypto-swing-bot/frontend && npm install && npm run build
```
Expected: install succeeds, `vite build` completes with a `dist/` and no errors.

- [ ] **Step 9: add `frontend/node_modules` and `frontend/dist` to the repo `.gitignore`** (append):
```gitignore
frontend/node_modules/
frontend/dist/
```

- [ ] **Step 10: Commit**
```bash
cd /home/redji/crypto-swing-bot && git add frontend/package.json frontend/vite.config.js frontend/index.html frontend/src/main.jsx frontend/src/api.js frontend/src/theme.css frontend/src/App.jsx .gitignore && git commit -m "feat(ui): scaffold Vite React app + Valhalla theme + api client"
```
(Do NOT commit node_modules or dist or package-lock if you prefer — but committing `package-lock.json` is fine and recommended for reproducibility; add it if present.)

---

## Task 2: Dashboard monitoring panels

**Files:** create `src/components/{StatusBanner,SignalPanel,PositionPanel,RiskPanel,JournalTable,MetricsPanel}.jsx`, `src/pages/Dashboard.jsx`

- [ ] **Step 1: `src/components/StatusBanner.jsx`**
```jsx
export default function StatusBanner({ state }){
  const halted = state?.kill_switch?.active
  const pnl = state?.day_pnl ?? 0
  return (
    <div className={`banner ${halted ? 'halted' : ''}`}>
      <span>● {state?.running ? (state?.paused ? 'PAUSED' : 'RUNNING') : 'STOPPED'}</span>
      <span>Regime: <b>{state?.signal?.regime ?? '—'}</b></span>
      <span>Day P&L: <b className={pnl>=0?'pos':'neg'}>{pnl>=0?'+':''}{pnl.toFixed?.(2) ?? pnl}</b></span>
      {halted && <span className="neg">⛔ KILL SWITCH: {state.kill_switch.reason}</span>}
    </div>
  )
}
```

- [ ] **Step 2: `src/components/SignalPanel.jsx`**
```jsx
export default function SignalPanel({ signal, symbol }){
  if (!signal) return <div className="panel"><h3>Signal</h3><div>—</div></div>
  if (signal.error) return <div className="panel"><h3>Signal</h3><div className="err">{signal.error}</div></div>
  const contrib = signal.contributions || {}
  return (
    <div className="panel">
      <h3>Signal — {symbol}</h3>
      {Object.entries(signal.signals || {}).map(([name, s])=>(
        <div className="row" key={name}>
          <span>{name}</span>
          <span>{(s.score ?? 0).toFixed(2)} → {(contrib[name] ?? 0).toFixed(3)}</span>
        </div>
      ))}
      <div className="row" style={{borderTop:'1px solid var(--line)',marginTop:6,paddingTop:6}}>
        <b>SCORE {(signal.score ?? 0).toFixed(3)} / {(signal.threshold ?? 0).toFixed(2)}</b>
        <span className={signal.passed?'pos':'neg'}>{signal.passed?'✓ would enter':'no'}</span>
      </div>
      <div className="row">Regime gate <span className={signal.permitted?'pos':'neg'}>{signal.permitted?'PASS':'VETO'}</span></div>
    </div>
  )
}
```

- [ ] **Step 3: `src/components/PositionPanel.jsx`**
```jsx
export default function PositionPanel({ position }){
  if (!position) return <div className="panel"><h3>Position</h3><div>Flat — waiting for signal</div></div>
  return (
    <div className="panel">
      <h3>Position</h3>
      <div className="row"><span>Entry</span><span>{position.entry_price}</span></div>
      <div className="row"><span>Qty</span><span>{position.qty}</span></div>
      <div className="row"><span>Stop</span><span className="neg">{position.stop?.toFixed?.(6)}</span></div>
      <div className="row"><span>Take-profit</span><span className="pos">{position.tp?.toFixed?.(6)}</span></div>
      <div className="row"><span>Max hold until</span><span>{position.max_hold_until}</span></div>
    </div>
  )
}
```

- [ ] **Step 4: `src/components/RiskPanel.jsx`**
```jsx
export default function RiskPanel({ state }){
  const ks = state?.kill_switch || {}
  return (
    <div className="panel">
      <h3>Risk</h3>
      <div className="row"><span>Kill switch</span><span className={ks.active?'neg':'pos'}>{ks.active?'TRIPPED':'armed'}</span></div>
      <div className="row"><span>Consecutive losses</span><span>{state?.consecutive_losses ?? 0}</span></div>
      <div className="row"><span>Mode</span><span>{state?.mode}</span></div>
    </div>
  )
}
```

- [ ] **Step 5: `src/components/JournalTable.jsx`**
```jsx
export default function JournalTable({ trades }){
  return (
    <div className="panel full">
      <h3>Journal</h3>
      <table><thead><tr>
        <th>Exit</th><th>Entry $</th><th>Exit $</th><th>P&L</th><th>Reason</th><th>Score</th><th>Regime</th>
      </tr></thead><tbody>
        {(trades||[]).slice(-25).reverse().map((t,i)=>(
          <tr key={i}>
            <td>{(t.exit_ts||'').slice(0,16)}</td><td>{t.entry_price?.toFixed?.(6)}</td>
            <td>{t.exit_price?.toFixed?.(6)}</td>
            <td className={t.pnl>=0?'pos':'neg'}>{t.pnl>=0?'+':''}{t.pnl?.toFixed?.(2)}</td>
            <td>{t.exit_reason}</td><td>{t.score_at_entry?.toFixed?.(2)}</td><td>{t.regime_at_entry}</td>
          </tr>
        ))}
        {(!trades || trades.length===0) && <tr><td colSpan="7">No trades yet</td></tr>}
      </tbody></table>
    </div>
  )
}
```

- [ ] **Step 6: `src/components/MetricsPanel.jsx`**
```jsx
export default function MetricsPanel({ metrics }){
  const m = metrics || {}
  const f = (x,d=2)=> (typeof x==='number' ? x.toFixed(d) : '—')
  return (
    <div className="panel full">
      <h3>Metrics</h3>
      <div className="row"><span>Expectancy / trade</span><span>{f(m.expectancy,4)}</span></div>
      <div className="row"><span>Win rate</span><span>{f((m.win_rate||0)*100,1)}%</span></div>
      <div className="row"><span>Profit factor</span><span>{f(m.profit_factor)}</span></div>
      <div className="row"><span>Max drawdown</span><span className="neg">{f(m.max_drawdown,2)}</span></div>
      <div className="row"><span>Trades</span><span>{m.n_trades ?? 0}</span></div>
    </div>
  )
}
```

- [ ] **Step 7: `src/pages/Dashboard.jsx`**
```jsx
import SignalPanel from '../components/SignalPanel.jsx'
import PositionPanel from '../components/PositionPanel.jsx'
import RiskPanel from '../components/RiskPanel.jsx'
import JournalTable from '../components/JournalTable.jsx'
import MetricsPanel from '../components/MetricsPanel.jsx'

export default function Dashboard({ state, trades, metrics }){
  return (
    <div className="wrap">
      <SignalPanel signal={state?.signal} symbol={state?.symbol} />
      <PositionPanel position={state?.position} />
      <RiskPanel state={state} />
      <div className="panel"><h3>Account</h3>
        <div className="row"><span>Symbol</span><span>{state?.symbol ?? '—'}</span></div>
        <div className="row"><span>Running</span><span>{String(state?.running)}</span></div>
      </div>
      <MetricsPanel metrics={metrics} />
      <JournalTable trades={trades} />
    </div>
  )
}
```

- [ ] **Step 8: build** — `cd /home/redji/crypto-swing-bot/frontend && npm run build` (clean).
- [ ] **Step 9: Commit** — `git add frontend/src/components frontend/src/pages/Dashboard.jsx && git commit -m "feat(ui): dashboard monitoring panels"`

---

## Task 3: Control bar

**Files:** create `src/components/ControlBar.jsx`

- [ ] **Step 1: `src/components/ControlBar.jsx`**
```jsx
import { useState } from 'react'
import { api } from '../api.js'

export default function ControlBar({ state, onChange }){
  const [err, setErr] = useState('')
  const run = async (fn) => { setErr(''); try { await fn(); onChange?.() } catch(e){ setErr(e.message) } }
  const confirmRun = (msg, fn) => { if (window.confirm(msg)) run(fn) }
  const paused = state?.paused
  return (
    <div className="panel full">
      <h3>Controls</h3>
      {err && <div className="err">{err}</div>}
      <button className="act danger" onClick={()=>confirmRun('Trip the kill switch (stop new entries)?', ()=>api.control('halt'))}>HALT</button>
      <button className="act" onClick={()=>run(()=>api.control('reset'))}>Reset kill switch</button>
      {paused
        ? <button className="act" onClick={()=>run(()=>api.control('resume'))}>Resume</button>
        : <button className="act" onClick={()=>run(()=>api.control('pause'))}>Pause entries</button>}
      <button className="act danger" onClick={()=>confirmRun('Flatten (market-sell) the open position now?', ()=>api.control('flatten'))}>Flatten</button>
      <button className="act danger" onClick={()=>confirmRun('Switch to LIVE (real money)? Server will block if not graduated.', async()=>{
        const r = await api.control('mode', { mode: 'live' }); if(!r.ok) throw new Error(r.reason)
      })}>Go LIVE</button>
      <button className="act" onClick={()=>run(async()=>{ const r=await api.control('mode',{mode:'paper'}); if(!r.ok) throw new Error(r.reason) })}>Go paper</button>
    </div>
  )
}
```

- [ ] **Step 2: build** (clean). **Step 3: Commit** — `git add frontend/src/components/ControlBar.jsx && git commit -m "feat(ui): control bar with confirmations"`

---

## Task 4: Strategy editor + Settings (credentials + token) + App shell

**Files:** create `src/components/TokenGate.jsx`, `src/pages/Strategy.jsx`, `src/pages/Settings.jsx`; replace `src/App.jsx`

- [ ] **Step 1: `src/components/TokenGate.jsx`**
```jsx
import { useState } from 'react'
import { getToken, setToken } from '../api.js'

export default function TokenGate({ onSet }){
  const [t, setT] = useState(getToken())
  return (
    <div className="panel">
      <h3>API token</h3>
      <p style={{color:'var(--muted)'}}>Paste the token printed by <code>swingbot-web</code> on startup. Stored in this browser only.</p>
      <input value={t} onChange={e=>setT(e.target.value)} placeholder="token" />
      <button className="act" style={{marginTop:10}} onClick={()=>{ setToken(t); onSet?.() }}>Save token</button>
    </div>
  )
}
```

- [ ] **Step 2: `src/pages/Strategy.jsx`**
```jsx
import { useEffect, useState } from 'react'
import { api } from '../api.js'

const DEFAULT = {
  symbol: 'TRX/USD', timeframe: '15m', entry_threshold: 0.3, regime_ma_period: 50,
  atr_period: 14, stop_atr_mult: 1.5, take_profit_atr_mult: 2.0, max_hold_bars: 32,
  risk_per_trade: 0.01, max_position_frac: 0.25,
  daily_loss_limit_pct: 0.05, max_consecutive_losses: 4, cooldown_minutes: 60,
  signals: { oversold: { weight: 0.6, oversold_level: 45, period: 14 },
             vwap: { weight: 0.4, window: 96, max_dist: 0.03 } },
}

export default function Strategy(){
  const [names, setNames] = useState([]); const [active, setActive] = useState(null)
  const [name, setName] = useState('trx'); const [json, setJson] = useState(JSON.stringify(DEFAULT, null, 2))
  const [err, setErr] = useState(''); const [msg, setMsg] = useState('')
  const load = async()=>{ setNames(await api.listProfiles()); const a = await api.activeProfile(); setActive(a.name) }
  useEffect(()=>{ load().catch(e=>setErr(e.message)) }, [])
  const save = async()=>{ setErr(''); setMsg(''); try{ await api.saveProfile(name, JSON.parse(json)); setMsg('saved'); load() }catch(e){ setErr(e.message) } }
  return (
    <div className="wrap">
      <div className="panel">
        <h3>Profiles</h3>
        {names.map(n=> <div className="row" key={n}>
          <span>{n} {active===n && <span className="chip">active</span>}</span>
          <span>
            <button className="act" onClick={()=>api.setActive(n).then(load).catch(e=>setErr(e.message))}>Set active</button>
            <button className="act danger" onClick={()=>api.deleteProfile(n).then(load)}>Delete</button>
          </span>
        </div>)}
        {names.length===0 && <div>No profiles yet — create one →</div>}
      </div>
      <div className="panel">
        <h3>Create / edit profile</h3>
        {err && <div className="err">{err}</div>}{msg && <div className="pos">{msg}</div>}
        <label>Name</label><input value={name} onChange={e=>setName(e.target.value)} />
        <label>Profile JSON (form-free editor)</label>
        <textarea style={{width:'100%',height:320,fontFamily:'monospace',background:'#0c1320',color:'var(--text)',border:'1px solid var(--line)',borderRadius:6,padding:8}}
          value={json} onChange={e=>setJson(e.target.value)} />
        <button className="act" style={{marginTop:10}} onClick={save}>Save profile</button>
      </div>
    </div>
  )
}
```
(Note: the strategy editor uses a JSON textarea seeded with sensible defaults. This is still "no files" — config is created/edited in the browser and persisted server-side. A field-by-field form is a future enhancement; the JSON editor keeps Phase 3B shippable.)

- [ ] **Step 3: `src/pages/Settings.jsx`**
```jsx
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import TokenGate from '../components/TokenGate.jsx'

export default function Settings(){
  const [st, setSt] = useState(null); const [err,setErr]=useState(''); const [msg,setMsg]=useState('')
  const [key, setKey] = useState(''); const [sec, setSec] = useState('')
  const [paper, setPaper] = useState(true)
  const load = async()=> setSt(await api.credStatus())
  useEffect(()=>{ load().catch(e=>setErr(e.message)) }, [])
  const save = async()=>{ setErr('');setMsg(''); try{
    const base = paper ? 'https://paper-api.alpaca.markets' : 'https://api.alpaca.markets'
    await api.setCreds(key, sec, base); setMsg('saved'); setSec(''); load()
  }catch(e){ setErr(e.message) } }
  return (
    <div className="wrap">
      <div className="panel">
        <h3>Alpaca credentials</h3>
        {err && <div className="err">{err}</div>}{msg && <div className="pos">{msg}</div>}
        <div className="row"><span>Stored key</span><span>{st?.key_id ?? '—'}</span></div>
        <div className="row"><span>Secret set</span><span className={st?.has_secret?'pos':'neg'}>{String(!!st?.has_secret)}</span></div>
        <label>Key ID</label><input value={key} onChange={e=>setKey(e.target.value)} />
        <label>Secret key (write-only)</label><input type="password" value={sec} onChange={e=>setSec(e.target.value)} placeholder="••••••••" />
        <label><input type="checkbox" style={{width:'auto'}} checked={paper} onChange={e=>setPaper(e.target.checked)} /> Paper endpoint</label>
        <button className="act" style={{marginTop:10}} onClick={save}>Save credentials</button>
      </div>
      <TokenGate onSet={()=>load().catch(()=>{})} />
    </div>
  )
}
```

- [ ] **Step 4: replace `src/App.jsx`**
```jsx
import { useEffect, useState, useCallback } from 'react'
import { api } from './api.js'
import Dashboard from './pages/Dashboard.jsx'
import Strategy from './pages/Strategy.jsx'
import Settings from './pages/Settings.jsx'
import StatusBanner from './components/StatusBanner.jsx'
import ControlBar from './components/ControlBar.jsx'

export default function App(){
  const [tab, setTab] = useState('dashboard')
  const [state, setState] = useState(null)
  const [trades, setTrades] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [err, setErr] = useState('')

  const refresh = useCallback(async()=>{
    try {
      const s = await api.state(); setState(s); setErr('')
      setTrades(await api.journal()); setMetrics(await api.metrics())
    } catch(e){ setErr(e.message) }
  }, [])

  useEffect(()=>{ refresh(); const id = setInterval(refresh, 2000); return ()=>clearInterval(id) }, [refresh])

  const live = state?.mode === 'live'
  return (
    <div>
      <div className="nav">
        <span className="brand">⚡ SwingBot</span>
        <button className={tab==='dashboard'?'active':''} onClick={()=>setTab('dashboard')}>Dashboard</button>
        <button className={tab==='strategy'?'active':''} onClick={()=>setTab('strategy')}>Strategy</button>
        <button className={tab==='settings'?'active':''} onClick={()=>setTab('settings')}>Settings</button>
        <span className={`mode ${live?'live':''}`}>{(state?.mode || 'paper').toUpperCase()}</span>
      </div>
      {tab==='dashboard' && <StatusBanner state={state} />}
      {err && <div className="err" style={{padding:'8px 20px'}}>{err}</div>}
      {tab==='dashboard' && <>
        <Dashboard state={state} trades={trades} metrics={metrics} />
        <div className="wrap"><ControlBar state={state} onChange={refresh} /></div>
      </>}
      {tab==='strategy' && <Strategy />}
      {tab==='settings' && <Settings />}
    </div>
  )
}
```

- [ ] **Step 5: build** — `npm run build` clean.
- [ ] **Step 6: Commit** — `git add frontend/src/App.jsx frontend/src/pages frontend/src/components/TokenGate.jsx && git commit -m "feat(ui): strategy editor, settings/credentials, app shell + tabs"`

---

## Task 5: End-to-end render verification + run docs

- [ ] **Step 1: Start the backend** (background): `cd /home/redji/crypto-swing-bot && . .venv/bin/activate && swingbot-web` — note the printed token. (If no `~/.swingbot/credentials.json`, that's fine; the UI handles unset creds.)
- [ ] **Step 2: Start the frontend dev server** (background): `cd frontend && npm run dev` (serves :3000, proxies /api → :8000).
- [ ] **Step 3: Render smoke via Playwright** — navigate to `http://localhost:3000`, confirm: nav shows "⚡ SwingBot" + PAPER chip; Dashboard renders panels (Signal/Position/Risk/Metrics/Journal/Controls) without a blank screen or console error; click Settings → credentials form renders; click Strategy → profile editor renders. Take a screenshot.
- [ ] **Step 4: Smoke the token + a write** — in Settings, paste the token (Save token), then save a profile in Strategy; confirm it appears in the profile list (verifies the X-Token write path end-to-end). 
- [ ] **Step 5: Stop the dev servers.**
- [ ] **Step 6: Write `frontend/README.md`** documenting: `swingbot-web` (backend, note the token), `cd frontend && npm install && npm run dev`, open http://localhost:3000, paste token in Settings, enter Alpaca paper creds, create + activate a strategy, watch the Dashboard. **Reiterate: localhost only — never expose port 8000/3000 to the internet.**
- [ ] **Step 7: Commit** — `git add frontend/README.md && git commit -m "docs(ui): how to run the dashboard"`

---

## What Phase 3B delivers
A Valhalla-styled React dashboard that runs the entire bot from the browser: live monitoring (signal breakdown, position, risk, journal, metrics) with 2s polling, a control bar (halt/reset/pause/resume/flatten/mode with confirmations and server-side go-live gating), a strategy editor that persists profiles server-side, and a credentials form (masked, write-only) — all over the Phase 3A API, localhost-only. Combined with Phases 1–3A, the project is now operable end-to-end without touching a file.
