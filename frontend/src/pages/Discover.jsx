import { useEffect, useState, useCallback } from 'react'
import { api } from '../api.js'

function fmtPct(x) { return x == null ? '—' : `${(x * 100).toFixed(1)}%` }
function fmtNum(x) { return x == null ? '—' : Number(x).toFixed(2) }
function ago(ts) {
  if (!ts) return 'never'
  const m = Math.round((Date.now() / 1000 - ts) / 60)
  return m < 1 ? 'just now' : `${m}m ago`
}
function expTier(x) {
  if (x == null) return ''
  if (x > 0.5) return 'tier-good'
  if (x > 0) return 'tier-ok'
  return 'tier-bad'
}

export default function Discover() {
  const [data, setData] = useState({ status: 'idle', rows: [], computed_at: null })
  const [windows, setWindows] = useState([{ key: 'full', label: 'Full history' }])
  const [window, setWindow] = useState('full')
  const [scope, setScope] = useState('universe')
  const [toast, setToast] = useState('')

  const load = useCallback(async () => {
    try { setData(await api.getDiscovery()) } catch { /* keep prior */ }
  }, [])

  useEffect(() => {
    load()
    api.discoveryWindows().then(setWindows).catch(() => {})
  }, [load])

  // poll while a sweep is computing
  useEffect(() => {
    if (data.status !== 'computing') return
    const id = setInterval(load, 2000)
    return () => clearInterval(id)
  }, [data.status, load])

  const refresh = async () => {
    await api.refreshDiscovery({ window, scope })
    load()
  }

  const arm = async (row) => {
    await api.armDiscovery(row.symbol, row.archetype, window)
    setToast(`Armed ${row.symbol} · ${row.label}`)
    setTimeout(() => setToast(''), 4000)
  }

  // group rows by coin
  const groups = {}
  for (const r of data.rows) (groups[r.symbol] ||= []).push(r)

  return (
    <div className="discover">
      <div className="discover-controls">
        <select value={window} onChange={(e) => setWindow(e.target.value)}>
          {windows.map((w) => <option key={w.key} value={w.key}>{w.label}</option>)}
        </select>
        <select value={scope} onChange={(e) => setScope(e.target.value)}>
          <option value="universe">Universe</option>
          <option value="watchlist">Watchlist</option>
        </select>
        <button onClick={refresh} disabled={data.status === 'computing'}>
          {data.status === 'computing' ? 'Computing…' : 'Refresh'}
        </button>
        <span className="discover-fresh">computed {ago(data.computed_at)}</span>
      </div>

      {toast && <p className="pos" role="status">{toast}</p>}
      {data.error && <p className="discover-error">Last sweep error: {data.error}</p>}
      {data.rows.length === 0 && data.status !== 'computing' &&
        <p className="muted">No results yet — hit Refresh to sweep the universe.</p>}

      {Object.entries(groups).map(([symbol, rows]) => (
        <div key={symbol} className="discover-coin">
          <h3>{symbol}</h3>
          <table className="discover-table">
            <thead>
              <tr><th>Strategy</th><th>Trades</th><th>Win</th><th>Exp</th>
                <th>PF</th><th>MaxDD</th><th>Now</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.archetype || 'err'} className={r.error ? 'row-err' : ''}>
                  <td>{r.label || '—'}</td>
                  <td>{r.metrics?.n_trades ?? '—'}</td>
                  <td>{fmtPct(r.metrics?.win_rate)}</td>
                  <td className={expTier(r.metrics?.expectancy)}>{fmtNum(r.metrics?.expectancy)}</td>
                  <td>{fmtNum(r.metrics?.profit_factor)}</td>
                  <td>{fmtPct(r.metrics?.max_drawdown)}</td>
                  <td>
                    {r.eligible_now && <span className="badge badge-eligible">eligible</span>}
                    {r.fires_now && <span className="dot dot-fires" title="signal fires now" />}
                  </td>
                  <td>{r.archetype &&
                    <button className="arm-btn" onClick={() => arm(r)}>Arm</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  )
}
