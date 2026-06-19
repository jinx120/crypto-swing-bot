import { api } from '../../api.js'
import usePolling from './usePolling.js'

export default function LiveStatsPanel() {
  const { data: trades } = usePolling(api.auto.trades, 10000)
  const list = trades || []
  const total = list.reduce((a, t) => a + Number(t.pnl || 0), 0)
  const wins = list.filter(t => t.won).length
  const winRate = list.length ? (wins / list.length) * 100 : 0
  const today = new Date().toISOString().slice(0, 10)
  const todayPnl = list
    .filter(t => (t.ts || '').slice(0, 10) === today)
    .reduce((a, t) => a + Number(t.pnl || 0), 0)
  return (
    <div className="panel">
      <h3>Live stats</h3>
      <div>Closed trades: <b>{list.length}</b></div>
      <div>Win rate: <b>{winRate.toFixed(1)}%</b></div>
      <div>Realized P&amp;L: <b style={{ color: total >= 0 ? '#36d17a' : '#ff5470' }}>
        {total >= 0 ? '+' : ''}{total.toFixed(2)}</b></div>
      <div>Today: <b>{todayPnl >= 0 ? '+' : ''}{todayPnl.toFixed(2)}</b></div>
    </div>
  )
}
