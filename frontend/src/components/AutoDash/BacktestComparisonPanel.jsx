import { api } from '../../api.js'
import usePolling from './usePolling.js'

function Card({ title, m }) {
  if (!m) return <div className="panel"><h3>{title}</h3><div>Loading…</div></div>
  const pnl = Number(m.total_pnl || 0)
  return (
    <div className="panel">
      <h3>{title}</h3>
      <div>Win rate: <b>{(Number(m.win_rate || 0) * 100).toFixed(1)}%</b></div>
      <div>Total P&amp;L: <b style={{ color: pnl >= 0 ? '#36d17a' : '#ff5470' }}>
        {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</b></div>
      <div>Sharpe: <b>{Number(m.sharpe || 0).toFixed(2)}</b></div>
      <div>Trades: <b>{m.n_trades ?? 0}</b></div>
    </div>
  )
}

export default function BacktestComparisonPanel() {
  // Backtest is cached server-side; a slow 60s poll is plenty.
  const ema = usePolling(api.auto.backtestEma, 60000)
  const kronos = usePolling(api.auto.backtestKronos, 60000)
  return (
    <div className="panel full">
      <h3>Backtest: EMA vs Kronos</h3>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <Card title="EMA momentum" m={ema.data} />
        <Card title="Kronos forecast" m={kronos.data} />
      </div>
    </div>
  )
}
