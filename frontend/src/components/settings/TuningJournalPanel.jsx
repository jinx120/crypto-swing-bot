import { useEffect, useMemo, useState } from 'react'
import { RotateCcw } from 'lucide-react'
import { api } from '../../api.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'
import { Button } from '../ui/button.jsx'
import { Badge } from '../ui/badge.jsx'

const valueText = (value) => (
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(4) : String(value ?? '')
)

export default function TuningJournalPanel() {
  const [rows, setRows] = useState([])
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const load = async () => {
    try {
      setRows(await api.getAdvisorJournal())
      setErr('')
    } catch (e) {
      setErr(e.message)
    }
  }

  useEffect(() => { load() }, [])

  const batches = useMemo(() => {
    const map = new Map()
    for (const row of rows) {
      if (!map.has(row.batch_id)) map.set(row.batch_id, [])
      map.get(row.batch_id).push(row)
    }
    return [...map.entries()].reverse()
  }, [rows])

  const revert = async (batchId) => {
    setErr('')
    setMsg('')
    try {
      await api.revertTuning(batchId)
      setMsg('reverted')
      await load()
    } catch (e) {
      setErr(e.message)
    }
  }

  const revertAll = async () => {
    setErr('')
    setMsg('')
    try {
      await api.revertAllTuning()
      setMsg('all reverted')
      await load()
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Tuning journal</CardTitle>
        <Button size="sm" variant="outline" onClick={revertAll} disabled={!rows.some((row) => !row.reverted)}>
          <RotateCcw className="h-3.5 w-3.5" /> Revert all
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {err && <div className="rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}
        {msg && <div className="rounded-md bg-up/15 px-3 py-2 text-sm text-up">{msg}</div>}
        {batches.length === 0 && <div className="text-sm text-muted-foreground">No tuning entries.</div>}
        {batches.map(([batchId, entries]) => {
          const reverted = entries.every((entry) => entry.reverted)
          return (
            <div key={batchId} className="rounded-md border border-border p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="text-xs text-muted-foreground">{batchId}</div>
                <div className="flex items-center gap-2">
                  <Badge variant={reverted ? 'default' : 'outline'}>{reverted ? 'reverted' : 'active'}</Badge>
                  <Button size="sm" variant="outline" disabled={reverted} onClick={() => revert(batchId)}>
                    <RotateCcw className="h-3.5 w-3.5" /> Revert
                  </Button>
                </div>
              </div>
              <div className="space-y-2">
                {entries.map((entry, index) => (
                  <div key={`${batchId}-${entry.symbol}-${entry.param}-${index}`} className="text-sm">
                    <div className="font-medium">{entry.symbol} · {entry.param}</div>
                    <div className="text-muted-foreground">
                      {valueText(entry.before)} → {valueText(entry.after)}
                      {entry.rationale ? ` · ${entry.rationale}` : ''}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </CardContent>
    </Card>
  )
}
