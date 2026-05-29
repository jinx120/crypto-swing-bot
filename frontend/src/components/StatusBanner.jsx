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
