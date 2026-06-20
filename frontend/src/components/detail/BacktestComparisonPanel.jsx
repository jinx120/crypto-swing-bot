import { api } from '../../api.js'
import usePolling from './usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

function Stat({ title, m }) {
  if (!m) return <div className="flex-1 rounded-md border border-border p-3"><div className="text-xs text-muted-foreground">{title}</div><div>Loading…</div></div>
  const pnl = Number(m.total_pnl || 0)
  return (
    <div className="flex-1 rounded-md border border-border p-3">
      <div className="mb-1 text-xs text-muted-foreground">{title}</div>
      <div className="text-sm">Win rate <b>{(Number(m.win_rate || 0) * 100).toFixed(1)}%</b></div>
      <div className="text-sm">P&amp;L <b className={pnl >= 0 ? 'text-up' : 'text-down'}>{pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}</b></div>
      <div className="text-sm">Sharpe <b>{Number(m.sharpe || 0).toFixed(2)}</b></div>
      <div className="text-sm">Trades <b>{m.n_trades ?? 0}</b></div>
    </div>
  )
}

export default function BacktestComparisonPanel({ symbol }) {
  const supported = symbol === 'BTC/USD'
  const ema = usePolling(supported ? api.auto.backtestEma : async () => null, 60000)
  const kronos = usePolling(supported ? api.auto.backtestKronos : async () => null, 60000)
  return (
    <Card>
      <CardHeader><CardTitle>Backtest: EMA vs Kronos</CardTitle></CardHeader>
      <CardContent>
        {!supported ? (
          <div className="text-sm text-muted-foreground">Backtest is single-symbol (BTC/USD) only.</div>
        ) : (
          <div className="flex flex-wrap gap-3">
            <Stat title="EMA momentum" m={ema.data} />
            <Stat title="Kronos forecast" m={kronos.data} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}
