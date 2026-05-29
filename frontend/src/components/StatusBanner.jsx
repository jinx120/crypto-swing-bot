import Hint from './Hint.jsx'

export default function StatusBanner({ state }){
  const halted = state?.kill_switch?.active
  const pnl = state?.day_pnl ?? 0
  const runState = state?.running ? (state?.paused ? 'PAUSED' : 'RUNNING') : 'STOPPED'
  return (
    <div className={`banner ${halted ? 'halted' : ''}`}>
      <span>● {runState}
        <Hint pos="below" text="RUNNING = the bot is checking each new price bar for an entry. PAUSED = still managing open trades but not opening new ones. STOPPED = the trading loop isn’t running." />
      </span>
      <span>Regime: <b>{state?.signal?.regime ?? '—'}</b>
        <Hint pos="below" text="The overall trend, measured against a moving average. The bot only opens new trades when the trend is up — this is the main guard against buying into a falling knife (a coin with no floor that keeps dropping)." />
      </span>
      <span>Day P&L: <b className={pnl>=0?'pos':'neg'}>{pnl>=0?'+':''}{pnl.toFixed?.(2) ?? pnl}</b>
        <Hint pos="below" text="Profit or loss from trades closed so far today, in account currency. If it falls past your daily loss limit, the kill switch trips and blocks new entries." />
      </span>
      {halted && <span className="neg">⛔ KILL SWITCH: {state.kill_switch.reason}</span>}
    </div>
  )
}
