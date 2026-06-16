import StrategyCard from '../components/StrategyCard.jsx'
import JournalTable from '../components/JournalTable.jsx'
import MetricsPanel from '../components/MetricsPanel.jsx'
import PositionGrid from '../components/PositionGrid.jsx'
import LifecycleBanner from '../components/LifecycleBanner.jsx'
import PendingOrders from '../components/PendingOrders.jsx'
import ReliabilityPanel from '../components/ReliabilityPanel.jsx'

export default function Dashboard({ state, trades, metrics, health, onChange }){
  const strategies = state?.strategies || []
  const mode = state?.portfolio?.mode
  return (
    <div className="wrap">
      <LifecycleBanner health={health} />
      <PositionGrid strategies={strategies} />
      <PendingOrders orders={state?.pending_orders || []} />
      {strategies.length === 0 && (
        <div className="panel full"><h3>No strategies armed</h3>
          <div>Arm one or more strategies on the <b>Strategy</b> tab to start trading them concurrently.</div>
        </div>
      )}
      {strategies.map(s => (
        <StrategyCard key={s.symbol || s.name} strategy={s} mode={mode}
          decision={health?.last_decisions_by_strategy?.[s.name]} onChange={onChange} />
      ))}
      <ReliabilityPanel health={health} />
      <MetricsPanel metrics={metrics} trades={trades} />
      <JournalTable trades={trades} />
    </div>
  )
}
