import ChartPanel from '../components/AutoDash/ChartPanel.jsx'
import CurrentPositionPanel from '../components/AutoDash/CurrentPositionPanel.jsx'
import LiveStatsPanel from '../components/AutoDash/LiveStatsPanel.jsx'
import RecentTradesPanel from '../components/AutoDash/RecentTradesPanel.jsx'
import BacktestComparisonPanel from '../components/AutoDash/BacktestComparisonPanel.jsx'
import JournalFeedPanel from '../components/AutoDash/JournalFeedPanel.jsx'

export default function AutoDashboard() {
  return (
    <div className="wrap">
      <ChartPanel />
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <CurrentPositionPanel />
        <LiveStatsPanel />
      </div>
      <BacktestComparisonPanel />
      <RecentTradesPanel />
      <JournalFeedPanel />
    </div>
  )
}
