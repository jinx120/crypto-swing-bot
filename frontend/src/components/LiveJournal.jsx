import { Card, CardContent, CardHeader, CardTitle } from './ui/card.jsx'
import { reliabilityPct } from '../lib/derive.js'

export default function LiveJournal({ health }) {
  const byStrat = health?.last_decisions_by_strategy || {}
  const rows = Object.values(byStrat)
    .map((d) => ({
      ts: d.bar_ts || d.completed_at || '',
      strategy: d.strategy,
      code: d.decision_code,
      reason: d.decision_reason,
    }))
    .sort((a, b) => (a.ts < b.ts ? 1 : -1))
  const rel = reliabilityPct(health)

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Decision Journal (live)</CardTitle>
        <span className="text-xs text-muted-foreground">
          reliability {rel == null ? '—' : `${rel.toFixed(0)}%`}
        </span>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <div className="text-sm text-muted-foreground">No decisions yet.</div>
        ) : (
          <div className="divide-y divide-border">
            {rows.map((r, i) => (
              <div key={i} className="flex items-baseline gap-3 py-1.5 text-sm">
                <span className="w-12 shrink-0 font-mono text-xs text-muted-foreground">
                  {(r.ts || '').slice(11, 16)}
                </span>
                <span className="w-24 shrink-0 truncate font-medium">{r.strategy}</span>
                <span className="shrink-0 font-mono text-xs font-semibold">{r.code}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground">{r.reason}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
