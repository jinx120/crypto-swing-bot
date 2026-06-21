import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

const pct = (value, digits = 1) => (
  typeof value === 'number' && Number.isFinite(value)
    ? `${(value * 100).toFixed(digits)}%`
    : '—'
)

export default function RebalancePanel(){
  const [status, setStatus] = useState(null)
  const [settings, setSettings] = useState(null)
  const [targets, setTargets] = useState({})
  const [err, setErr] = useState('')
  const [msg, setMsg] = useState('')

  const load = async () => {
    const [nextStatus, nextSettings, nextTargets] = await Promise.all([
      api.getRebalanceStatus(),
      api.getRebalanceSettings(),
      api.getRebalanceTargets(),
    ])
    setStatus(nextStatus)
    setSettings(nextSettings)
    setTargets(nextTargets.targets || {})
  }

  useEffect(() => {
    let alive = true
    const refresh = async () => {
      try {
        const [nextStatus, nextSettings, nextTargets] = await Promise.all([
          api.getRebalanceStatus(),
          api.getRebalanceSettings(),
          api.getRebalanceTargets(),
        ])
        if (!alive) return
        setStatus(nextStatus)
        setSettings(nextSettings)
        setTargets(nextTargets.targets || {})
        setErr('')
      } catch (e) {
        if (alive) setErr(e.message)
      }
    }
    refresh()
    const id = setInterval(refresh, 10000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  // Weights auto-derive (equal-weight across active coins; the advisor tunes them).
  // This panel is read-only by design — no manual numbers to set.
  const rows = useMemo(() => {
    const allocs = status?.allocations || []
    const names = new Set([...allocs.map((a) => a.name), ...Object.keys(targets)])
    return [...names].sort().map((name) => {
      const alloc = allocs.find((a) => a.name === name)
      return {
        name,
        symbol: alloc?.symbol || '',
        target: targets[name] ?? alloc?.target_weight ?? 0,
        actual: alloc?.actual_weight ?? 0,
        drift: alloc?.drift ?? 0,
      }
    })
  }, [status, targets])

  const canRun = settings?.enabled && settings?.mode === 'hard'

  const patchSettings = async (patch) => {
    setErr(''); setMsg('')
    try {
      const next = { ...settings, ...patch }
      setSettings(next)
      await api.setRebalanceSettings(patch)
      setMsg('saved')
      await load()
    } catch (e) {
      setErr(e.message)
    }
  }

  const runNow = async () => {
    setErr(''); setMsg('')
    try {
      await api.runRebalance()
      setMsg('queued')
      await load()
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <div className="panel full rebalance-panel">
      <h3>Rebalance</h3>
      {err && <div className="err">{err}</div>}
      {msg && <div className="pos">{msg}</div>}
      <div className="rebalance-grid">
        <div>
          <div className="rebalance-controls">
            <label>
              <input
                type="checkbox"
                style={{ width: 'auto' }}
                checked={!!settings?.enabled}
                onChange={(e) => patchSettings({ enabled: e.target.checked })}
              /> Enabled
            </label>
            <label>Mode
              <select
                value={settings?.mode || 'soft'}
                onChange={(e) => patchSettings({ mode: e.target.value })}
              >
                <option value="soft">soft</option>
                <option value="hard">hard</option>
              </select>
            </label>
          </div>
          <div className="row"><span>Drift threshold</span><span>{pct(settings?.drift_threshold)}</span></div>
          <div className="row"><span>Min interval</span><span>{settings?.min_interval_minutes ?? '—'} min</span></div>
          <div className="row"><span>Fee rate</span><span>{pct(settings?.fee_rate, 2)}</span></div>
          <div className="row"><span>Last run</span><span>{status?.last_rebalance_at || '—'}</span></div>
          <div className="row"><span>Next eligible</span><span>{status?.next_eligible_at || '—'}</span></div>
          <div className="row"><span>Last skip</span><span>{status?.last_skip_reason || '—'}</span></div>
          <button className="act" disabled={!canRun} onClick={runNow}>Rebalance now</button>
        </div>
        <div>
          <table>
            <thead>
              <tr><th>Strategy</th><th>Target</th><th>Actual</th><th>Drift</th><th></th></tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const over = row.drift > (settings?.drift_threshold || 0)
                return (
                  <tr key={row.name} className={over ? 'rebalance-over' : ''}>
                    <td>{row.name}<span className="muted-cell">{row.symbol}</span></td>
                    <td>{pct(row.target)}</td>
                    <td>{pct(row.actual)}</td>
                    <td className={row.drift >= 0 ? 'pos' : 'neg'}>{pct(row.drift)}</td>
                    <td><div className="drift-bar"><span style={{ width: `${Math.min(Math.abs(row.drift) * 100, 100)}%` }} /></div></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className="row muted-cell">Weights auto-derive (equal-weight); the advisor tunes them.</div>
        </div>
      </div>
    </div>
  )
}
