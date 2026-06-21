import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card, CardContent, CardHeader, CardTitle } from './ui/card.jsx'

export default function AdvisorNotes() {
  const [notes, setNotes] = useState([])
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const rows = await api.getAdvisorNotes()
        if (!alive) return
        setNotes(rows.slice(-6).reverse())
        setErr('')
      } catch (e) {
        if (alive) setErr(e.message)
      }
    }
    load()
    const id = setInterval(load, 10000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  return (
    <Card>
      <CardHeader><CardTitle>Advisor notes</CardTitle></CardHeader>
      <CardContent>
        {err && <div className="rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}
        {!err && notes.length === 0 && (
          <div className="text-sm text-muted-foreground">No advisor notes yet.</div>
        )}
        <div className="space-y-2">
          {notes.map((note, index) => (
            <div key={`${note.batch_id}-${note.symbol}-${note.param}-${index}`} className="rounded-md border border-border px-3 py-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium">{note.symbol} · {note.param}</span>
                <span className="text-xs text-muted-foreground">{note.ts || ''}</span>
              </div>
              <div className="mt-1 text-muted-foreground">{note.rationale}</div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
