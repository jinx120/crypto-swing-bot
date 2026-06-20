import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Scale } from 'lucide-react'
import { api } from '../api.js'
import { Badge } from './ui/badge.jsx'

export default function RebalanceStrip() {
  const [status, setStatus] = useState(null)
  useEffect(() => {
    let alive = true
    const tick = () => api.getRebalanceStatus().then((s) => { if (alive) setStatus(s) }).catch(() => {})
    tick()
    const id = setInterval(tick, 10000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const enabled = status?.enabled
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-2.5 text-sm">
      <Scale className="h-4 w-4 text-muted-foreground" />
      <span className="font-medium">Rebalance</span>
      {!enabled ? (
        <span className="text-muted-foreground">off</span>
      ) : (
        <>
          <Badge variant="outline">{status.mode}</Badge>
          {status.last_skip_reason
            ? <span className="text-muted-foreground">{status.last_skip_reason}</span>
            : <span className="text-up">on target</span>}
          {status.next_eligible_at &&
            <span className="text-muted-foreground">next ≥ {status.next_eligible_at.slice(11, 16)}</span>}
        </>
      )}
      <Link to="/settings" className="ml-auto text-muted-foreground hover:text-foreground">configure →</Link>
    </div>
  )
}
