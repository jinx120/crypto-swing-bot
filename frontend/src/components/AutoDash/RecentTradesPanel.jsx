import { api } from '../../api.js'
import usePolling from './usePolling.js'

export default function RecentTradesPanel() {
  const { data: trades } = usePolling(api.auto.trades, 10000)
  const list = trades || []
  return (
    <div className="panel">
      <h3>Recent trades</h3>
      {list.length === 0 ? <div>No closed trades yet.</div> : (
        <table style={{ width: '100%' }}>
          <thead><tr><th>Time</th><th>P&amp;L</th><th>Result</th><th>Reason</th></tr></thead>
          <tbody>
            {list.map((t, i) => (
              <tr key={i}>
                <td>{(t.ts || '').replace('T', ' ').slice(0, 16)}</td>
                <td style={{ color: t.pnl >= 0 ? '#36d17a' : '#ff5470' }}>
                  {t.pnl >= 0 ? '+' : ''}{Number(t.pnl).toFixed(2)}</td>
                <td>{t.won ? 'WIN' : 'LOSS'}</td>
                <td>{t.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
