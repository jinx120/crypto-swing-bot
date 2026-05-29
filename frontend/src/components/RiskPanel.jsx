import Hint from './Hint.jsx'

export default function RiskPanel({ state }){
  const ks = state?.kill_switch || {}
  return (
    <div className="panel">
      <h3>Risk
        <Hint text="The safety layer. These circuit breakers stop the bot from digging a deeper hole during a bad run." />
      </h3>
      <div className="row"><span>Kill switch
        <Hint text="Master safety halt. When TRIPPED, the bot opens no new trades but keeps managing open ones (their stop/target stay live). Trips on the daily loss limit or too many losses in a row; clear it with “Reset kill switch.”" /></span><span className={ks.active?'neg':'pos'}>{ks.active?'TRIPPED':'armed'}</span></div>
      <div className="row"><span>Consecutive losses
        <Hint text="How many losing trades have closed back-to-back. Reaching your configured max trips the kill switch — protection against a losing streak." /></span><span>{state?.consecutive_losses ?? 0}</span></div>
      <div className="row"><span>Mode
        <Hint text="paper = simulated money (safe). live = real money. Configured in the Settings tab and the top-right badge." /></span><span>{state?.mode}</span></div>
    </div>
  )
}
