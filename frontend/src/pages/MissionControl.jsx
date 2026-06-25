import { useCallback, useEffect, useState } from 'react'
import StatusStrip from '../components/StatusStrip.jsx'
import CoinsGrid from '../components/CoinsGrid.jsx'
import RebalanceStrip from '../components/RebalanceStrip.jsx'
import LiveJournal from '../components/LiveJournal.jsx'
import AddCoinDialog from '../components/AddCoinDialog.jsx'
import AdvisorNotes from '../components/AdvisorNotes.jsx'
import useLivePrice from '../components/useLivePrice.js'
import { api } from '../api.js'
import { readCache, writeCache } from '../lib/cache.js'

export default function MissionControl() {
  const [state, setState] = useState(() => readCache('swingbot:state'))
  const [health, setHealth] = useState(() => readCache('swingbot:health'))
  const [addOpen, setAddOpen] = useState(false)
  const symbols = (state?.strategies || []).map((s) => s.symbol).filter(Boolean)
  const prices = useLivePrice(symbols)

  const refresh = useCallback(async () => {
    try { const s = await api.state(); setState(s); writeCache('swingbot:state', s) } catch { /* keep last */ }
    try { const h = await api.tradingHealth(); setHealth(h); writeCache('swingbot:health', h) } catch { /* keep last */ }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 3000)
    return () => clearInterval(id)
  }, [refresh])

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <StatusStrip state={state} health={health} onChange={refresh} />
      <CoinsGrid state={state} health={health} prices={prices} onChange={refresh} onAdd={() => setAddOpen(true)} />
      <RebalanceStrip />
      <AdvisorNotes />
      <LiveJournal health={health} />
      <AddCoinDialog open={addOpen} onOpenChange={setAddOpen} onAdded={refresh} />
    </div>
  )
}
