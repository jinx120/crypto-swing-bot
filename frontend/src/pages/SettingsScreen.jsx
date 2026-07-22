import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Card } from '../components/ui/card.jsx'
import BrokerConnectionPanel from '../components/settings/BrokerConnectionPanel.jsx'

export default function SettingsScreen() {
  const [mode, setMode] = useState('paper')
  const [err, setErr] = useState('')

  useEffect(() => {
    api.state().then((s) => setMode(s?.portfolio?.mode || 'paper')).catch(() => {})
  }, [])

  async function pickMode(m) {
    try { await api.control('mode', { mode: m }); setMode(m); setErr('') }
    catch (e) { setErr(e.message) }
  }

  return (
    <div className="mx-auto max-w-md space-y-4 p-4">
      {err && <div className="text-sm text-red-500">{err}</div>}

      <BrokerConnectionPanel />

      <Card className="space-y-2 p-4">
        <div className="text-xs uppercase text-muted-foreground">Mode</div>
        {['paper', 'live'].map((m) => (
          <label key={m} className="flex cursor-pointer items-center gap-2 text-sm capitalize">
            <input type="radio" name="mode" checked={m === mode} onChange={() => pickMode(m)} />
            {m} trading
          </label>
        ))}
      </Card>

      <Card className="space-y-2 p-4">
        <div className="text-xs uppercase text-muted-foreground">Notifications (optional)</div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input type="checkbox" disabled /> Trade alerts (coming soon)
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input type="checkbox" disabled /> Drawdown warnings (coming soon)
        </label>
      </Card>
    </div>
  )
}
