import SignalPanel from '../components/SignalPanel.jsx'
import PositionPanel from '../components/PositionPanel.jsx'
import RiskPanel from '../components/RiskPanel.jsx'
import JournalTable from '../components/JournalTable.jsx'
import MetricsPanel from '../components/MetricsPanel.jsx'

export default function Dashboard({ state, trades, metrics }){
  return (
    <div className="wrap">
      <SignalPanel signal={state?.signal} symbol={state?.symbol} />
      <PositionPanel position={state?.position} />
      <RiskPanel state={state} />
      <div className="panel"><h3>Account</h3>
        <div className="row"><span>Symbol</span><span>{state?.symbol ?? '—'}</span></div>
        <div className="row"><span>Running</span><span>{String(state?.running)}</span></div>
      </div>
      <MetricsPanel metrics={metrics} />
      <JournalTable trades={trades} />
    </div>
  )
}
