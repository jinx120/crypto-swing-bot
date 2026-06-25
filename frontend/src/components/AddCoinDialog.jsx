import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog.jsx'
import { Button } from './ui/button.jsx'
import { Badge } from './ui/badge.jsx'
import { availableToAdd } from '../lib/derive.js'

export default function AddCoinDialog({ open, onOpenChange, onAdded }) {
  const [options, setOptions] = useState([])
  const [watchlist, setWatchlist] = useState({ symbols: [] })
  const [strategies, setStrategies] = useState([])
  const [researched, setResearched] = useState([])
  const [universe, setUniverse] = useState([])
  const [preset, setPreset] = useState('')
  const [symbol, setSymbol] = useState('')
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!open) return
    setErr('')
    Promise.all([api.universe(), api.watchlist(), api.strategies(), api.listResearched()])
      .then(([u, w, s, r]) => {
        setOptions(availableToAdd(u, w))
        setWatchlist(w)
        setStrategies(s)
        setResearched(r)
        setUniverse(u.symbols || [])
      })
      .catch((e) => setErr(e.message))
  }, [open])

  const add = async (symbol) => {
    setBusy(symbol); setErr('')
    try {
      await api.setWatchlist([...(watchlist.symbols || []), symbol])
      const match = strategies.find((st) => st.symbol === symbol)
      if (match) await api.arm(match.name)
      await onAdded?.()
      onOpenChange(false)
    } catch (e) { setErr(e.message) } finally { setBusy('') }
  }

  const addResearched = async () => {
    if (!preset || !symbol) {
      setErr('pick a preset and a symbol')
      return
    }
    setBusy('researched')
    setErr('')
    try {
      await api.addResearched(preset, symbol)
      await onAdded?.()
      onOpenChange(false)
    } catch (e) { setErr(e.message) } finally { setBusy('') }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add coin</DialogTitle></DialogHeader>
        {err && <div className="mb-2 rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}

        <div className="text-xs font-semibold text-muted-foreground">Kronos (default)</div>
        <div className="max-h-48 space-y-1 overflow-y-auto">
          {options.length === 0
            ? <div className="p-3 text-center text-sm text-muted-foreground">All symbols already added.</div>
            : options.map((sym) => (
              <button key={sym} disabled={busy === sym} onClick={() => add(sym)}
                className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-50">
                <span className="font-medium">{sym}</span>
                <span className="text-xs text-muted-foreground">{busy === sym ? 'adding…' : 'add →'}</span>
              </button>
            ))}
        </div>

        <div className="mt-4 flex items-center gap-2">
          <span className="text-xs font-semibold text-muted-foreground">Researched strategies</span>
          <Badge variant="outline" className="text-down">backtested negative-edge — demo only</Badge>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select className="rounded border bg-background px-2 py-1 text-sm"
            value={preset} onChange={(e) => setPreset(e.target.value)}>
            <option value="">preset...</option>
            {researched.map((r) => <option key={r.preset} value={r.preset}>{r.label}</option>)}
          </select>
          <select className="rounded border bg-background px-2 py-1 text-sm"
            value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            <option value="">symbol...</option>
            {universe.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <Button size="sm" variant="outline" disabled={busy === 'researched'}
            onClick={addResearched}>{busy === 'researched' ? 'adding...' : 'arm demo'}</Button>
        </div>

        <div className="mt-3 flex justify-end">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Close</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
