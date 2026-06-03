import { useEffect, useState } from 'react'
import { api } from '../api.js'
import ChartPanel from './ChartPanel.jsx'

// Grid of mini charts: one tile per open position, then a watchlist row.
export default function PositionGrid({ strategies = [] }){
  const [watchlist, setWatchlist] = useState([])
  useEffect(() => { api.watchlist().then(r => setWatchlist(r.symbols)).catch(() => {}) }, [])

  const open = strategies.filter(s => s.position)
  const heldSymbols = new Set(open.map(s => s.symbol))
  const watchOnly = watchlist.filter(sym => !heldSymbols.has(sym))

  return (
    <div className="wrap">
      <div className="panel full">
        <h3>Open positions {open.length > 0 && <span className="chip">{open.length}</span>}</h3>
        {open.length === 0 && <div className="muted">No open positions. Arm a strategy on the Strategy tab.</div>}
        <div className="position-grid">
          {open.map(s => (
            <div className="pg-tile" key={s.symbol || s.name}>
              <div className="pg-head">{s.symbol}</div>
              <ChartPanel symbol={s.symbol} mini position={s.position} />
            </div>
          ))}
        </div>
      </div>

      {watchOnly.length > 0 && (
        <div className="panel full">
          <h3>Watchlist</h3>
          <div className="position-grid">
            {watchOnly.map(sym => (
              <div className="pg-tile" key={sym}>
                <div className="pg-head">{sym}</div>
                <ChartPanel symbol={sym} mini />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
