import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api.js'
import { Card, CardContent } from './ui/card.jsx'
import { Badge } from './ui/badge.jsx'
import { Button } from './ui/button.jsx'
import MiniChart from './MiniChart.jsx'
import { cn } from '../lib/utils.js'
import { cardStatus, lastDecision } from '../lib/derive.js'

const STATUS_VARIANT = { long: 'up', short: 'down', flat: 'default', armed: 'outline' }

export default function CoinCard({ strategy, health, onChange }) {
  const nav = useNavigate()
  const [busy, setBusy] = useState(false)
  const status = cardStatus(strategy)
  const pos = strategy.position
  const unreal = pos?.unrealized
  const decision = lastDecision(health, strategy.name)
  const hasPosition = !!pos && status !== 'armed'

  const act = async (fn) => {
    setBusy(true)
    try { await fn(); await onChange?.() } catch (e) { alert(e.message) } finally { setBusy(false) }
  }

  return (
    <Card
      className="cursor-pointer transition-colors hover:border-primary/50"
      onClick={() => nav(`/coin/${encodeURIComponent(strategy.name)}`)}
    >
      <CardContent className="space-y-3 p-4">
        <div className="flex items-center justify-between">
          <span className="font-semibold">{strategy.symbol || strategy.label}</span>
          <Badge variant={STATUS_VARIANT[status]}>{status}</Badge>
        </div>
        <div className="font-mono tabular-nums text-sm">
          {hasPosition ? (
            <>
              <div className="text-muted-foreground">
                {Number(pos.qty)} @ {Number(pos.entry_price).toFixed(2)}
              </div>
              <div className={cn('text-lg font-semibold', (unreal ?? 0) >= 0 ? 'text-up' : 'text-down')}>
                {unreal == null ? '—' : `${unreal >= 0 ? '+' : ''}${unreal.toFixed(2)}`}
              </div>
              {(pos.tp != null || pos.stop != null) && (
                <div className="flex gap-3 text-xs text-muted-foreground">
                  <span>🎯 {pos.tp != null ? Number(pos.tp).toFixed(2) : '—'}</span>
                  <span>🛑 {pos.stop != null ? Number(pos.stop).toFixed(2) : '—'}</span>
                </div>
              )}
            </>
          ) : (
            <div className="text-muted-foreground">—</div>
          )}
        </div>
        {strategy.symbol && <MiniChart symbol={strategy.symbol} />}
        <div className="min-h-[2.5rem] text-xs text-muted-foreground">
          {decision ? <><b className="text-foreground">{decision.code}</b> · {decision.reason}</> : 'no recent decision'}
        </div>
        <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
          {status === 'armed'
            ? <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => api.arm(strategy.name))}>arm</Button>
            : <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => api.disarm(strategy.name))}>disarm</Button>}
          {hasPosition &&
            <Button size="sm" variant="danger" disabled={busy} onClick={() => act(() => api.flattenStrategy(strategy.name))}>flatten</Button>}
        </div>
      </CardContent>
    </Card>
  )
}
