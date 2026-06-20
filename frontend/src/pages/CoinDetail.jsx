import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { api } from '../api.js'
import { Button } from '../components/ui/button.jsx'
import { Badge } from '../components/ui/badge.jsx'
import { cardStatus } from '../lib/derive.js'
import ChartPanel from '../components/detail/ChartPanel.jsx'
import CurrentPositionPanel from '../components/detail/CurrentPositionPanel.jsx'
import LiveStatsPanel from '../components/detail/LiveStatsPanel.jsx'
import RecentTradesPanel from '../components/detail/RecentTradesPanel.jsx'
import BacktestComparisonPanel from '../components/detail/BacktestComparisonPanel.jsx'
import JournalFeedPanel from '../components/detail/JournalFeedPanel.jsx'

export default function CoinDetail() {
  const { name } = useParams()
  const strategyName = decodeURIComponent(name)
  const nav = useNavigate()
  const [state, setState] = useState(null)
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try { setState(await api.state()) } catch { /* keep last */ }
  }, [])
  useEffect(() => { refresh(); const id = setInterval(refresh, 3000); return () => clearInterval(id) }, [refresh])

  const strat = (state?.strategies || []).find((s) => s.name === strategyName)
  const symbol = strat?.symbol
  const status = strat ? cardStatus(strat) : 'armed'
  const hasPosition = !!strat?.position && status !== 'armed'

  const act = async (fn) => { setBusy(true); try { await fn(); await refresh() } catch (e) { alert(e.message) } finally { setBusy(false) } }
  const removeFromWatchlist = async () => {
    const w = await api.watchlist()
    await api.setWatchlist((w.symbols || []).filter((s) => s !== symbol))
    if (status !== 'armed') await api.disarm(strategyName)
    nav('/')
  }

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <div className="flex items-center gap-3">
        <Link to="/" className="text-muted-foreground hover:text-foreground"><ArrowLeft className="h-5 w-5" /></Link>
        <h1 className="text-lg font-semibold">{symbol || strategyName}</h1>
        <Badge variant="outline">{status}</Badge>
        <div className="ml-auto flex gap-2">
          {status === 'armed'
            ? <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => api.arm(strategyName))}>arm</Button>
            : <Button size="sm" variant="outline" disabled={busy} onClick={() => act(() => api.disarm(strategyName))}>disarm</Button>}
          {hasPosition && <Button size="sm" variant="danger" disabled={busy} onClick={() => act(() => api.flattenStrategy(strategyName))}>flatten</Button>}
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => act(removeFromWatchlist)}>remove</Button>
        </div>
      </div>

      {!strat ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          Strategy “{strategyName}” is not currently armed.
        </div>
      ) : (
        <>
          <ChartPanel symbol={symbol} strategy={strategyName} />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <CurrentPositionPanel strategy={strat} />
            <LiveStatsPanel strategy={strategyName} />
          </div>
          <BacktestComparisonPanel symbol={symbol} />
          <RecentTradesPanel strategy={strategyName} />
          <JournalFeedPanel strategy={strategyName} />
        </>
      )}
    </div>
  )
}
