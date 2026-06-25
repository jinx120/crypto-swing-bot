import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle } from 'lucide-react'
import { api } from '../api.js'
import { Button } from './ui/button.jsx'
import { Badge } from './ui/badge.jsx'
import { Skeleton } from './ui/skeleton.jsx'
import { cn } from '../lib/utils.js'
import {
  loopState, modeBadge, equityOf, dayPnl, dayPnlPct, openPnl, reliabilityPct, brokerUnauthorized,
} from '../lib/derive.js'

function Dot({ ok, label }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
      <span className={cn('h-1.5 w-1.5 rounded-full', ok ? 'bg-up' : 'bg-down')} /> {label}
    </span>
  )
}

export default function StatusStrip({ state, health, onChange }) {
  const [busy, setBusy] = useState(false)
  const loop = loopState(health)
  const running = loop === 'RUNNING'
  const eq = equityOf(state)
  const pnl = dayPnl(state)
  const pct = dayPnlPct(state)
  const open = openPnl(state)
  const rel = reliabilityPct(health)
  const noBroker = brokerUnauthorized(health)

  const toggle = async () => {
    setBusy(true)
    try { await api.control(running ? 'stop' : 'start'); await onChange?.() }
    catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  const loopColor = loop === 'RUNNING' ? 'bg-up' : loop === 'PAUSED' ? 'bg-warn' : 'bg-muted-foreground'

  if (!state) return <Skeleton className="h-12 w-full" />

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-border bg-card px-4 py-3">
        <div className="flex items-center gap-2">
          <span className={cn('h-2.5 w-2.5 rounded-full', loopColor)} />
          <span className="font-semibold">{loop}</span>
          <Badge variant="outline">{modeBadge(state)}</Badge>
        </div>
        <div className="text-sm">
          equity <span className="font-mono tabular-nums font-semibold">
            {eq == null ? '—' : `$${eq.toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          </span>
        </div>
        <div className="text-sm">
          today{' '}
          <span className={cn('font-mono tabular-nums font-semibold', (pnl ?? 0) >= 0 ? 'text-up' : 'text-down')}>
            {pnl == null ? '—' : `${pnl >= 0 ? '▲ +' : '▼ '}${pnl.toFixed(2)}`}
            {pct != null && ` (${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%)`}
          </span>
        </div>
        <div className="text-sm">
          open{' '}
          <span className={cn('font-mono tabular-nums font-semibold', (open ?? 0) >= 0 ? 'text-up' : 'text-down')}>
            {open == null ? '—' : `${open >= 0 ? '+' : ''}${open.toFixed(2)}`}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-4">
          <Dot ok={!!state} label="backend" />
          <Dot ok={!noBroker} label="broker" />
          <Dot ok={rel == null ? true : rel >= 90} label={`reliability ${rel == null ? '—' : rel.toFixed(0) + '%'}`} />
          <Button variant={running ? 'danger' : 'default'} size="sm" disabled={busy} onClick={toggle}>
            {running ? 'Stop' : 'Start'}
          </Button>
        </div>
      </div>
      {noBroker && (
        <Link to="/settings"
          className="flex items-center gap-2 rounded-lg border border-warn/40 bg-warn/10 px-4 py-2 text-sm text-warn">
          <AlertTriangle className="h-4 w-4" />
          Broker not connected — fix in Settings →
        </Link>
      )}
    </div>
  )
}
