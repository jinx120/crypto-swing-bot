import { useEffect, useState } from 'react'
import { api } from '../../api.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'
import { Label } from '../ui/label.jsx'

const LABELS = {
  coinbase: 'Coinbase',
  kraken: 'Kraken',
  alpaca: 'Alpaca',
}

export default function DataSourcePanel() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')
  const [saving, setSaving] = useState(false)

  const load = async () => {
    const next = await api.getDataSource()
    setData(next)
  }

  useEffect(() => { load().catch((e) => setErr(e.message)) }, [])

  const setSource = async (value) => {
    setErr('')
    setMsg('')
    setSaving(true)
    try {
      const next = await api.setDataSource(value)
      setData((prev) => ({ choices: prev?.choices || [], data_source: next.data_source }))
      setMsg('Saved')
    } catch (e) {
      setErr(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (!data) return <Card><CardContent className="p-4">Loading...</CardContent></Card>

  return (
    <Card>
      <CardHeader><CardTitle>Data source</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {err && <div className="rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}
        {msg && <div className="rounded-md bg-up/15 px-3 py-2 text-sm text-up">{msg}</div>}
        <div className="space-y-1">
          <Label>Data source</Label>
          <select
            value={data.data_source}
            disabled={saving}
            onChange={(e) => setSource(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            {(data.choices || []).map((source) => (
              <option key={source} value={source}>{LABELS[source] || source}</option>
            ))}
          </select>
        </div>
      </CardContent>
    </Card>
  )
}
