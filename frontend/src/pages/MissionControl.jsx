import { useCallback, useEffect, useState } from 'react'
import StatusStrip from '../components/StatusStrip.jsx'
import CoinsGrid from '../components/CoinsGrid.jsx'
import RebalanceStrip from '../components/RebalanceStrip.jsx'
import LiveJournal from '../components/LiveJournal.jsx'
import AddCoinDialog from '../components/AddCoinDialog.jsx'
import { api } from '../api.js'

export default function MissionControl() {
  const [state, setState] = useState(null)
  const [health, setHealth] = useState(null)
  const [addOpen, setAddOpen] = useState(false)

  const refresh = useCallback(async () => {
    try { setState(await api.state()) } catch { /* keep last */ }
    try { setHealth(await api.tradingHealth()) } catch { /* keep last */ }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 3000)
    return () => clearInterval(id)
  }, [refresh])

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <StatusStrip state={state} health={health} onChange={refresh} />
      <CoinsGrid state={state} health={health} onChange={refresh} onAdd={() => setAddOpen(true)} />
      <RebalanceStrip />
      <LiveJournal health={health} />
      <AddCoinDialog open={addOpen} onOpenChange={setAddOpen} onAdded={refresh} />
    </div>
  )
}
