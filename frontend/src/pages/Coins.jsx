import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card } from '../components/ui/card.jsx'
import { Button } from '../components/ui/button.jsx'
import { Input } from '../components/ui/input.jsx'

export default function Coins() {
  const [coins, setCoins] = useState([])
  const [level, setLevel] = useState('Moderate')
  const [choices, setChoices] = useState(['Conservative', 'Moderate', 'Aggressive'])
  const [symbol, setSymbol] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  async function refresh() {
    try {
      const [c, r] = await Promise.all([api.coins(), api.riskLevel()])
      setCoins(c || [])
      setLevel(r.risk_level)
      setChoices(r.choices || choices)
      setErr('')
    } catch (e) { setErr(e.message) }
  }

  useEffect(() => { refresh() }, [])

  async function add(e) {
    e.preventDefault()
    if (!symbol.trim()) return
    setBusy(true)
    try { await api.addCoin(symbol.trim()); setSymbol(''); await refresh() }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function remove(name) {
    setBusy(true)
    try { await api.removeCoin(name); await refresh() }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  async function pickLevel(l) {
    setBusy(true)
    try { await api.setRiskLevel(l); setLevel(l) }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="mx-auto max-w-md space-y-4 p-4">
      {err && <div className="text-sm text-red-500">{err}</div>}

      <Card className="space-y-3 p-4">
        <div className="text-xs uppercase text-muted-foreground">Trading</div>
        {coins.length === 0 && <div className="text-sm text-muted-foreground">No coins yet.</div>}
        {coins.map((c) => (
          <div key={c.name} className="flex items-center justify-between text-sm">
            <span className="inline-flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              {c.symbol}
            </span>
            <button className="text-muted-foreground hover:text-red-500"
              disabled={busy} onClick={() => remove(c.name)}>x</button>
          </div>
        ))}
        <form onSubmit={add} className="flex gap-2 pt-2">
          <Input placeholder="Add coin (e.g. SOL)" value={symbol}
            onChange={(e) => setSymbol(e.target.value)} />
          <Button type="submit" disabled={busy}>Add</Button>
        </form>
      </Card>

      <Card className="space-y-2 p-4">
        <div className="text-xs uppercase text-muted-foreground">Risk Level</div>
        {choices.map((l) => (
          <label key={l} className="flex cursor-pointer items-center gap-2 text-sm">
            <input type="radio" name="risk" checked={l === level} disabled={busy}
              onChange={() => pickLevel(l)} />
            {l}
          </label>
        ))}
      </Card>
    </div>
  )
}
