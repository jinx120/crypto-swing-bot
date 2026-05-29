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
