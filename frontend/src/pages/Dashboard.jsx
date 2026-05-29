import SignalPanel from '../components/SignalPanel.jsx'
import PositionPanel from '../components/PositionPanel.jsx'
import RiskPanel from '../components/RiskPanel.jsx'
import JournalTable from '../components/JournalTable.jsx'
import MetricsPanel from '../components/MetricsPanel.jsx'
import Hint from '../components/Hint.jsx'

export default function Dashboard({ state, trades, metrics }){
  return (
    <div className="wrap">
      <SignalPanel signal={state?.signal} symbol={state?.symbol} />
      <PositionPanel position={state?.position} />
      <RiskPanel state={state} />
      <div className="panel"><h3>Account
        <Hint text="What the bot is set to trade and whether its loop is live. The active strategy profile (set in the Strategy tab) decides the symbol." />
      </h3>
        <div className="row"><span>Symbol
          <Hint text="The crypto pair this run is trading, e.g. TRX/USD. Comes from the active strategy profile." /></span><span>{state?.symbol ?? '—'}</span></div>
        <div className="row"><span>Running
          <Hint text="true = the trading loop is alive and checking each new bar. false = stopped (no monitoring, no trading)." /></span><span>{String(state?.running)}</span></div>
      </div>
      <MetricsPanel metrics={metrics} />
      <JournalTable trades={trades} />
    </div>
  )
}
