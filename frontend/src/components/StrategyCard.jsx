import { useEffect, useState } from 'react'
import { api } from '../api.js'
import ChartPanel from './ChartPanel.jsx'
import SignalPanel from './SignalPanel.jsx'
import PositionPanel from './PositionPanel.jsx'
import Hint from './Hint.jsx'

const fmtTs = (iso) => iso ? new Date(iso).toLocaleString() : '-'

export default function StrategyCard({ strategy, mode, decision, onChange }){
  const [err, setErr] = useState('')
  const [trades, setTrades] = useState([])
  const s = strategy || {}

  useEffect(() => {
    if (!s.name) {
      setTrades([])
      return
    }
    let live = true
    api.journal(s.name).then(t => { if (live) setTrades(t || []) }).catch(() => {})
    return () => { live = false }
  }, [s.name])

  const run = async (fn, confirmMsg) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return
    setErr('')
    try { await fn(); onChange?.() } catch (e) { setErr(e.message) }
  }
  const paperOnly = mode === 'live' && !s.live_eligible
  const isProbe = s.kind === 'probe'
  const pos = s.position
  const unreal = pos?.unrealized

  return (
    <div className="panel full strategy-card">
      <h3>{s.label || s.name} - {s.symbol}
        <Hint text="One armed strategy trading one symbol. Its signal, position, and controls are scoped to this card." />
        {isProbe
          ? <span className="chip" title="Deterministic proof-of-life probe, not a trading strategy">probe</span>
          : <span className="chip" title="Managed or user trading strategy">strategy</span>}
        {isProbe && s.probe_complete != null && (
          <span className={`chip ${s.probe_complete ? '' : 'warn'}`}
            title="Whether the one-shot probe has fired and recorded its durable completion marker">
            {s.probe_complete ? 'probe complete' : 'probe pending'}</span>)}
        {paperOnly && <span className="chip warn" title="Armed but not live-eligible - manages open trades but opens none in LIVE mode">paper-only</span>}
      </h3>
      {err && <div className="err">{err}</div>}

      <div className="row"><span>Last decision
        <Hint text="The terminal decision code from the most recent completed strategy cycle, with the human reason and the bar timestamp it was based on." /></span>
        <span>{decision ? decision.decision_code : '-'}</span></div>
      {decision && (
        <div className="row"><span className="muted">{decision.decision_reason}</span>
          <span className="muted">bar {fmtTs(decision.bar_ts)}</span></div>)}

      {pos && (
        <div className="row"><span>Unrealized P&amp;L
          <Hint text="Mark-to-market gain/loss on the open position: (mark price - entry) x qty, using the latest local close. Source timestamp shown alongside." /></span>
          <span className={unreal == null ? '' : (unreal >= 0 ? 'pos' : 'neg')}>
            {unreal == null ? '-' : unreal.toFixed(2)}
            {pos.mark_price != null && <span className="muted"> @ {pos.mark_price} - {fmtTs(pos.mark_ts)}</span>}
          </span></div>)}

      <ChartPanel symbol={s.symbol} mini position={pos} trades={trades} showMarkersInMini />
      <div className="card-cols">
        <SignalPanel signal={s.snapshot} symbol={s.symbol} />
        <PositionPanel position={pos} />
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
