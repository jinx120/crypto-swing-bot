import { useEffect, useState, useCallback } from 'react'
import { api } from './api.js'
import Dashboard from './pages/Dashboard.jsx'
import Strategy from './pages/Strategy.jsx'
import Settings from './pages/Settings.jsx'
import Guide from './pages/Guide.jsx'
import StatusBanner from './components/StatusBanner.jsx'
import ControlBar from './components/ControlBar.jsx'
import Hint from './components/Hint.jsx'

export default function App(){
  const [tab, setTab] = useState('dashboard')
  const [state, setState] = useState(null)
  const [trades, setTrades] = useState([])
  const [metrics, setMetrics] = useState(null)
  const [err, setErr] = useState('')
  const [unreachable, setUnreachable] = useState(false)

  const refresh = useCallback(async()=>{
    try {
      const s = await api.state(); setState(s); setErr(''); setUnreachable(false)
      setTrades(await api.journal()); setMetrics(await api.metrics())
    } catch(e){ setErr(e.message); setUnreachable(!!e.network) }
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
        <button className={`help ${tab==='guide'?'active':''}`} title="Trading guide" onClick={()=>setTab('guide')}>?</button>
        <span className={`mode ${live?'live':''}`}>{(state?.mode || 'paper').toUpperCase()}
          <Hint pos="below" text={live
            ? 'LIVE: the bot is trading real money on your Alpaca account. Every fill is a real buy/sell.'
            : 'PAPER: simulated money on Alpaca’s test server — safe for trying things out. The bot blocks switching to LIVE until your paper results pass the graduation checks.'} />
        </span>
      </div>
      {unreachable && <div className="err" style={{padding:'10px 20px'}}>
        Cannot reach the backend. The dashboard can't resolve or connect to its API host.
        Check that <code>swingbot-web</code> is running and that you're loading this page
        from a resolvable host (or via the Vite <code>/api</code> proxy on port 3000).
      </div>}
      {tab==='dashboard' && <StatusBanner state={state} />}
      {err && <div className="err" style={{padding:'8px 20px'}}>{err}</div>}
      {tab==='dashboard' && <>
        <Dashboard state={state} trades={trades} metrics={metrics} />
        <div className="wrap"><ControlBar state={state} onChange={refresh} /></div>
      </>}
      {tab==='strategy' && <Strategy />}
      {tab==='settings' && <Settings />}
      {tab==='guide' && <Guide />}
    </div>
  )
}
