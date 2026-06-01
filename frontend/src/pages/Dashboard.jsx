import StrategyCard from '../components/StrategyCard.jsx'
import JournalTable from '../components/JournalTable.jsx'
import MetricsPanel from '../components/MetricsPanel.jsx'

export default function Dashboard({ state, trades, metrics, onChange }){
  const strategies = state?.strategies || []
  const mode = state?.portfolio?.mode
  return (
    <div className="wrap">
      {strategies.length === 0 && (
        <div className="panel full"><h3>No strategies armed</h3>
          <div>Arm one or more strategies on the <b>Strategy</b> tab to start trading them concurrently.</div>
        </div>
      )}
      {strategies.map(s => (
        <StrategyCard key={s.symbol || s.name} strategy={s} mode={mode} onChange={onChange} />
      ))}
      <MetricsPanel metrics={metrics} />
      <JournalTable trades={trades} />
    </div>
  )
}
