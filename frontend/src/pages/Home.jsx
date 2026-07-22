import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card } from '../components/ui/card.jsx'
import { Button } from '../components/ui/button.jsx'
import { formatMoney, formatSignedPct, formatSignedMoney } from '../lib/format.js'

const WINDOWS = ['24h', '7d', '30d']

export default function Home() {
  const [state, setState] = useState(null)
  const [pnl, setPnl] = useState(null)
  const [recent, setRecent] = useState([])
  const [window, setWindow] = useState('24h')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function refresh() {
    try {
      const [s, p, d] = await Promise.all([
        api.state(), api.portfolioPnl(), api.decisions(undefined, 8),
      ])
      setState(s); setPnl(p); setRecent(d || []); setErr('')
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [])

  const portfolio = state?.portfolio || {}
  const running = !!portfolio.running
  const strategies = state?.strategies || []
  const positions = strategies.filter((s) => s.position)
  const win = pnl?.[window] || { abs: 0, pct: 0 }

  async function toggle() {
    setBusy(true)
    try { await api.control(running ? 'stop' : 'start'); await refresh() }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="mx-auto max-w-md space-y-4 p-4">
      <div className="flex items-center justify-between">
        <span className={`inline-flex items-center gap-2 text-sm font-medium ${running ? 'text-emerald-500' : 'text-muted-foreground'}`}>
          <span className={`h-2 w-2 rounded-full ${running ? 'bg-emerald-500' : 'bg-muted-foreground'}`} />
          {running ? 'Running' : 'Stopped'}
        </span>
        <Button variant={running ? 'danger' : 'default'} disabled={busy} onClick={toggle}>
          {running ? 'Stop' : 'Start'}
        </Button>
      </div>

      {err && <div className="text-sm text-red-500">{err}</div>}

      <Card className="space-y-3 p-4">
        <div className="text-xs uppercase text-muted-foreground">Portfolio</div>
        <div className="text-3xl font-semibold">{formatMoney(portfolio.equity)}</div>
        <div className={`text-sm ${win.abs >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
          {formatSignedMoney(win.abs)} ({formatSignedPct(win.pct)})
        </div>
        <div className="flex gap-2">
          {WINDOWS.map((w) => (
            <button key={w} onClick={() => setWindow(w)}
              className={`rounded-md px-2.5 py-1 text-xs ${w === window ? 'bg-accent text-foreground' : 'text-muted-foreground'}`}>
              {w}
            </button>
          ))}
        </div>
        {portfolio.defensive && (
          <div className="rounded-md bg-amber-500/10 px-3 py-2 text-xs text-amber-500">
            {portfolio.autotuner_status || 'Defensive mode - recovering from recent losses.'}
          </div>
        )}
      </Card>

      <Card className="space-y-2 p-4">
        <div className="text-xs uppercase text-muted-foreground">Open Positions</div>
        {positions.length === 0 && <div className="text-sm text-muted-foreground">No open positions.</div>}
        {positions.map((s) => {
          const pos = s.position
          const qty = Number(pos.qty || 0)
          const up = (pos.unrealized ?? 0) >= 0
          return (
            <div key={s.name} className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-3 text-sm">
              <span className="font-medium">{s.symbol}</span>
              <span className="text-muted-foreground">{qty.toFixed(4)}</span>
              <span>{pos.mark_price ? formatMoney(qty * pos.mark_price) : '-'}</span>
              <span className={up ? 'text-emerald-500' : 'text-red-500'}>
                {pos.unrealized != null ? formatSignedMoney(pos.unrealized) : '-'}
              </span>
            </div>
          )
        })}
      </Card>

      <Card className="space-y-2 p-4">
        <div className="text-xs uppercase text-muted-foreground">Recent Activity</div>
        {recent.length === 0 && <div className="text-sm text-muted-foreground">Nothing yet.</div>}
        {recent.map((d, i) => (
          <div key={i} className="flex items-center justify-between gap-3 text-sm">
            <span className="font-medium">{(d.strategy || '').replace('kronos-', '').replace('-', '/').toUpperCase()}</span>
            <span className="text-muted-foreground">{d.decision_code}</span>
            <span className="text-xs text-muted-foreground">{d.bar_ts ? new Date(d.bar_ts).toLocaleTimeString() : ''}</span>
          </div>
        ))}
      </Card>
    </div>
  )
}
