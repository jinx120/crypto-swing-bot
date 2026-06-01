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
