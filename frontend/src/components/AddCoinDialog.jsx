import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog.jsx'
import { Button } from './ui/button.jsx'
import { availableToAdd } from '../lib/derive.js'

export default function AddCoinDialog({ open, onOpenChange, onAdded }) {
  const [options, setOptions] = useState([])
  const [watchlist, setWatchlist] = useState({ symbols: [] })
  const [strategies, setStrategies] = useState([])
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!open) return
    setErr('')
    Promise.all([api.universe(), api.watchlist(), api.strategies()])
      .then(([u, w, s]) => { setOptions(availableToAdd(u, w)); setWatchlist(w); setStrategies(s) })
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

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Add coin</DialogTitle></DialogHeader>
        {err && <div className="mb-2 rounded-md bg-down/15 px-3 py-2 text-sm text-down">{err}</div>}
        <div className="max-h-72 space-y-1 overflow-y-auto">
          {options.length === 0
            ? <div className="p-4 text-center text-sm text-muted-foreground">All available symbols are already added.</div>
            : options.map((sym) => (
              <button key={sym} disabled={busy === sym} onClick={() => add(sym)}
                className="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-50">
                <span className="font-medium">{sym}</span>
                <span className="text-xs text-muted-foreground">{busy === sym ? 'adding…' : 'add →'}</span>
              </button>
            ))}
        </div>
        <div className="mt-3 flex justify-end">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>Close</Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
