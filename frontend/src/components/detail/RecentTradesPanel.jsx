import { useMemo } from 'react'
import { api } from '../../api.js'
import usePolling from './usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

export default function RecentTradesPanel({ strategy }) {
  const fetcher = useMemo(() => () => api.journal(strategy), [strategy])
  const { data: trades } = usePolling(fetcher, 10000)
  const list = trades || []
  return (
    <Card>
      <CardHeader><CardTitle>Recent trades</CardTitle></CardHeader>
      <CardContent>
        {list.length === 0 ? <div className="text-sm text-muted-foreground">No closed trades yet.</div> : (
          <table className="w-full text-sm">
            <thead><tr className="text-left text-xs text-muted-foreground">
              <th className="font-medium">Time</th><th className="font-medium">P&amp;L</th><th className="font-medium">Result</th><th className="font-medium">Reason</th>
            </tr></thead>
            <tbody>
              {list.map((t, i) => (
                <tr key={i} className="border-t border-border">
                  <td className="py-1 font-mono text-xs">{(t.exit_ts || '').replace('T', ' ').slice(0, 16)}</td>
                  <td className={`font-mono ${t.pnl >= 0 ? 'text-up' : 'text-down'}`}>{t.pnl >= 0 ? '+' : ''}{Number(t.pnl).toFixed(2)}</td>
                  <td>{t.pnl >= 0 ? 'WIN' : 'LOSS'}</td>
                  <td className="text-muted-foreground">{t.exit_reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  )
}
