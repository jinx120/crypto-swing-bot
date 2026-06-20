import { useMemo } from 'react'
import { api } from '../../api.js'
import usePolling from './usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

export default function JournalFeedPanel({ strategy }) {
  const fetcher = useMemo(() => () => api.journal(strategy), [strategy])
  const { data: trades } = usePolling(fetcher, 10000)
  const list = (trades || []).slice().sort((a, b) => (a.exit_ts < b.exit_ts ? 1 : -1))
  return (
    <Card>
      <CardHeader><CardTitle>Decision journal</CardTitle></CardHeader>
      <CardContent>
        <div className="max-h-72 space-y-1 overflow-y-auto">
          {list.length === 0 ? <div className="text-sm text-muted-foreground">No events yet.</div> : list.map((t, i) => (
            <div key={i} className="border-b border-border py-1 text-sm">
              <span className="text-muted-foreground">{(t.exit_ts || '').replace('T', ' ').slice(0, 16)} </span>
              <b>{t.exit_reason}</b> — {t.pnl >= 0 ? '+' : ''}{Number(t.pnl).toFixed(2)}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
