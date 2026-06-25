import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import usePolling from './detail/usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card.jsx'
import { cn } from '../lib/utils.js'
import { reliabilityPct } from '../lib/derive.js'

// Codes that represent action/entry vs. a block — used for a subtle row accent.
const GOOD = /ENTER|SUBMIT|EXIT|FILL/i
const BAD = /BLOCK|BELOW|FAIL|ERROR|INVALID|ZERO/i

function codeClass(code) {
  if (GOOD.test(code)) return 'text-up'
  if (BAD.test(code)) return 'text-down'
  return 'text-foreground'
}

function fmtVal(v) {
  if (typeof v !== 'number') return String(v)
  if (Number.isInteger(v)) return String(v)
  return Math.abs(v) >= 1 ? v.toFixed(2) : v.toFixed(4)
}

export default function LiveJournal({ health }) {
  const [filter, setFilter] = useState('') // '' = all strategies
  const [known, setKnown] = useState([]) // stable strategy list for the dropdown
  const [open, setOpen] = useState(() => new Set()) // expanded row keys

  const fetcher = useMemo(
    () => () => api.decisions(filter || undefined, 500),
    [filter],
  )
  const { data } = usePolling(fetcher, 10000)

  const rows = (data || []).map((d, i) => ({
    key: `${d.strategy}-${d.cycle_id ?? i}-${d.completed_at ?? i}`,
    ts: d.bar_ts || d.completed_at || '',
    strategy: d.strategy,
    code: d.decision_code,
    reason: d.decision_reason,
    details: d.decision_details || {},
  }))

  // Accumulate every strategy we have ever seen (plus armed ones from health) so
  // the filter dropdown stays stable instead of collapsing when a filter hides
  // the others.
  useEffect(() => {
    const fromHealth = Object.keys(health?.last_decisions_by_strategy || {})
    const fromRows = rows.map((r) => r.strategy).filter(Boolean)
    setKnown((prev) => {
      const next = new Set([...prev, ...fromHealth, ...fromRows])
      return next.size === prev.length ? prev : [...next].sort()
    })
  }, [data, health]) // eslint-disable-line react-hooks/exhaustive-deps

  const rel = reliabilityPct(health)
  const toggle = (k) =>
    setOpen((prev) => {
      const next = new Set(prev)
      next.has(k) ? next.delete(k) : next.add(k)
      return next
    })

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between gap-2">
        <CardTitle>Decision Journal (live)</CardTitle>
        <div className="flex items-center gap-3">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="rounded border border-border bg-background px-2 py-1 text-xs"
          >
            <option value="">all strategies</option>
            {known.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <span className="text-xs text-muted-foreground">
            {rows.length} · reliability {rel == null ? '—' : `${rel.toFixed(0)}%`}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <div className="text-sm text-muted-foreground">No decisions yet.</div>
        ) : (
          <div className="max-h-[28rem] divide-y divide-border overflow-y-auto">
            {rows.map((r) => {
              const isOpen = open.has(r.key)
              const entries = Object.entries(r.details)
              return (
                <div key={r.key}>
                  <button
                    type="button"
                    onClick={() => toggle(r.key)}
                    className="flex w-full items-baseline gap-3 py-1.5 text-left text-sm hover:bg-muted/40"
                  >
                    <span className="w-3 shrink-0 text-xs text-muted-foreground">
                      {entries.length ? (isOpen ? '▾' : '▸') : ''}
                    </span>
                    <span className="w-28 shrink-0 font-mono text-xs text-muted-foreground">
                      {(r.ts || '').replace('T', ' ').slice(5, 16)}
                    </span>
                    <span className="w-24 shrink-0 truncate font-medium">{r.strategy}</span>
                    <span className={cn('shrink-0 font-mono text-xs font-semibold', codeClass(r.code))}>
                      {r.code}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-muted-foreground">{r.reason}</span>
                  </button>
                  {isOpen && entries.length > 0 && (
                    <div className="ml-[8.75rem] flex flex-wrap gap-x-4 gap-y-1 pb-2 text-xs">
                      {entries.map(([k, v]) => (
                        <span key={k} className="font-mono">
                          <span className="text-muted-foreground">{k}:</span> {fmtVal(v)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
