import { useEffect, useState } from 'react'
import { api } from '../../api.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'
import { Button } from '../ui/button.jsx'
import { Input } from '../ui/input.jsx'
import { Label } from '../ui/label.jsx'

export default function BrokerConnectionPanel() {
  const [data, setData] = useState(null)
  const [sel, setSel] = useState('')
  const [vals, setVals] = useState({})
  const [mode, setMode] = useState('paper')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const load = async () => { const d = await api.listBrokers(); setData(d); setSel((prev) => prev || d.active) }
  useEffect(() => { load().catch((e) => setErr(e.message)) }, [])
  useEffect(() => { setVals({}); setMsg(''); setErr('') }, [sel])

  if (!data) return <Card><CardContent className="p-4">Loading…</CardContent></Card>
  const broker = data.brokers.find((b) => b.id === sel) || data.brokers[0]
  const setField = (n, v) => setVals((s) => ({ ...s, [n]: v }))
  const valuesPayload = () => {
    const out = { ...vals }
    if (broker.modes.includes('paper'))
      out.base_url = mode === 'paper' ? 'https://paper-api.alpaca.markets' : 'https://api.alpaca.markets'
    return out
  }
  const doTest = async () => { setErr(''); setMsg(''); try { const r = await api.testBroker(broker.id, valuesPayload(), mode); r.ok ? setMsg(`Test OK — ${r.detail}`) : setErr(`Test failed — ${r.detail}`) } catch (e) { setErr(e.message) } }
  const doSave = async () => { setErr(''); setMsg(''); try { await api.setBrokerCreds(broker.id, valuesPayload()); if (data.active !== broker.id) await api.setActiveBroker(broker.id); setMsg('Saved'); setVals({}); load() } catch (e) { setErr(e.message) } }
  const doReconnect = async () => { setErr(''); setMsg(''); try { const r = await api.reconnectBroker(); r.ok ? setMsg(`Reconnected — ${r.detail}`) : setErr(`Reconnect failed — ${r.detail}`) } catch (e) { setErr(e.message) } }

  return (
    <Card>
      <CardHeader><CardTitle>Broker connection</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {err && <div className="rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}
        {msg && <div className="rounded-md bg-up/15 px-3 py-2 text-sm text-up">{msg}</div>}
        <div className="space-y-1">
          <Label>Broker</Label>
          <select value={sel} onChange={(e) => setSel(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm">
            {data.brokers.map((b) => (
              <option key={b.id} value={b.id}>
                {b.label}{b.id === data.active ? ' (active)' : ''}{b.configured ? ' ✓' : ''}
              </option>
            ))}
          </select>
        </div>
        {broker.fields.map((f) => (
          <div key={f.name} className="space-y-1">
            <Label>{f.label}
              {broker.status.fields[f.name]?.set && !f.secret && <span className="ml-1 text-muted-foreground">(current: {broker.status.fields[f.name].value})</span>}
              {broker.status.fields[f.name]?.set && f.secret && <span className="ml-1 text-up">(set)</span>}
            </Label>
            <Input type={f.secret ? 'password' : 'text'} value={vals[f.name] || ''}
              placeholder={f.secret ? '••••••••' : ''} onChange={(e) => setField(f.name, e.target.value)} />
          </div>
        ))}
        {broker.modes.includes('paper') && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={mode === 'paper'} onChange={(e) => setMode(e.target.checked ? 'paper' : 'live')} />
            Paper endpoint
          </label>
        )}
        <div className="flex gap-2 pt-1">
          <Button size="sm" variant="outline" onClick={doTest}>Test connection</Button>
          <Button size="sm" onClick={doSave}>Save credentials</Button>
          <Button size="sm" variant="outline" onClick={doReconnect}>Reconnect bot</Button>
        </div>
      </CardContent>
    </Card>
  )
}
