import Hint from './Hint.jsx'

export default function LifecycleBanner({ health }) {
  const lc = health?.lifecycle
  if (!lc) return null

  const desired = lc.running_desired
  const actual = lc.running_actual
  const statusLabel = { active: 'ACTIVE', inactive: 'STOPPED', unhealthy: 'UNHEALTHY' }[health.status] || '-'
  const statusColor = health.status === 'active' ? 'var(--green)'
    : health.status === 'inactive' ? 'var(--muted)' : 'var(--red)'
  const desiredText = desired === true ? 'yes' : desired === false ? 'no' : 'unknown'

  return (
    <div className="panel full">
      <h3>Bot lifecycle
        <Hint text="Desired = whether you asked the bot to run (survives restarts). Actual = whether the loop thread is really alive right now. They should match; a mismatch means a failed start or crash." />
        <span className="chip" style={{ marginLeft: 8, color: statusColor }}>{statusLabel}</span>
      </h3>
      <div className="row"><span>Desired running</span><span>{desiredText}</span></div>
      <div className="row"><span>Actually running</span>
        <span className={actual ? 'pos' : 'neg'}>{actual ? 'yes' : 'no'}</span></div>
      <div className="row"><span>Mode</span><span>{(lc.mode || 'paper').toUpperCase()}</span></div>
      {lc.paused && <div className="row"><span>Paused</span><span className="neg">yes</span></div>}
      {lc.halted && <div className="row"><span>Halted (kill switch)</span><span className="neg">yes</span></div>}
      {lc.running_desired_error && (
        <div className="err">Desire unreadable: {lc.running_desired_error}</div>)}
      {lc.startup_error && (
        <div className="err">Startup error: {lc.startup_error}</div>)}
    </div>
  )
}
