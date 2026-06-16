import Hint from './Hint.jsx'

const fmtTs = (iso) => iso ? new Date(iso).toLocaleString() : '-'
const pct = (x) => (typeof x === 'number' ? `${(x * 100).toFixed(1)}%` : '-')

export default function ReliabilityPanel({ health }) {
  const r = health?.reliability
  if (!r) return null

  const stages = r.stages || {}
  return (
    <div className="panel full">
      <h3>Trading reliability
        <Hint text="Per-stage success rate over the latest completed cycles. Each rate is shown with ok/failed/skipped counts and the time window, never as a bare percentage." />
      </h3>
      <div className="row"><span>Window</span>
        <span className="muted">{fmtTs(r.window_started_at)} - {fmtTs(r.window_completed_at)}</span></div>
      <div className="row"><span>Completed cycles</span>
        <span>{r.completed_cycles ?? 0}
          <span className="muted"> ({r.successful_cycles ?? 0} successful)</span></span></div>
      <div className="row"><span>Cycle completion</span>
        <span>{pct(r.cycle_completion_ratio)}
          <span className="muted"> ({r.successful_cycles ?? 0}/{r.completed_cycles ?? 0})</span></span></div>
      <div className="row"><span>Critical-stage floor</span>
        <span>{pct(r.critical_stage_floor)}</span></div>
      {Object.entries(stages).map(([name, st]) => (
        <div className="row" key={name}><span>{name}</span>
          <span>{pct(st.ratio)}
            <span className="muted"> ({st.ok ?? 0}/{st.samples ?? 0} ok, {st.failed ?? 0} failed, {st.skipped ?? 0} skipped)</span></span>
        </div>))}
    </div>
  )
}
