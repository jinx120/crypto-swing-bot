import { useEffect, useState } from 'react'
import { api } from '../../api.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'
import { Label } from '../ui/label.jsx'

const OPTIONS = [
  ['cautious', 'Cautious'],
  ['balanced', 'Balanced'],
  ['aggressive', 'Aggressive'],
]

export default function RiskDialPanel() {
  const [dial, setDial] = useState('balanced')
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    let alive = true
    api.getRiskDial()
      .then((data) => { if (alive) setDial(data.risk_dial || 'balanced') })
      .catch((e) => { if (alive) setErr(e.message) })
    return () => { alive = false }
  }, [])

  const save = async (value) => {
    setDial(value)
    setErr('')
    setMsg('')
    try {
      const data = await api.setRiskDial(value)
      setDial(data.risk_dial)
      setMsg('saved')
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <Card>
      <CardHeader><CardTitle>Risk dial</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        {err && <div className="rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}
        {msg && <div className="rounded-md bg-up/15 px-3 py-2 text-sm text-up">{msg}</div>}
        <Label className="block">Mode
          <select
            className="mt-1 h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={dial}
            onChange={(e) => save(e.target.value)}
          >
            {OPTIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Label>
      </CardContent>
    </Card>
  )
}
