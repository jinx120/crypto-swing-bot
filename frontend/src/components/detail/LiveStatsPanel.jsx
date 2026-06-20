import { useMemo } from 'react'
import { api } from '../../api.js'
import usePolling from './usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

export default function LiveStatsPanel({ strategy }) {
  const fetcher = useMemo(() => () => api.metrics(strategy), [strategy])
  const { data: m } = usePolling(fetcher, 10000)
  const pnl = Number(m?.total_pnl || 0)
  return (
    <Card>
      <CardHeader><CardTitle>Live stats</CardTitle></CardHeader>
      <CardContent className="space-y-1 text-sm">
        <div className="flex justify-between"><span className="text-muted-foreground">Trades</span><span className="font-mono">{m?.n_trades ?? 0}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Win rate</span><span className="font-mono">{((Number(m?.win_rate || 0)) * 100).toFixed(1)}%</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Realized P&amp;L</span>
          <span className={`font-mono ${pnl >= 0 ? 'text-up' : 'text-down'}`}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</span></div>
        <div className="flex justify-between"><span className="text-muted-foreground">Sharpe</span><span className="font-mono">{Number(m?.sharpe || 0).toFixed(2)}</span></div>
      </CardContent>
    </Card>
  )
}
