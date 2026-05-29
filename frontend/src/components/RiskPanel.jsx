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
