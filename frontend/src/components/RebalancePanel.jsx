import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'

const pct = (value, digits = 1) => (
  typeof value === 'number' && Number.isFinite(value)
    ? `${(value * 100).toFixed(digits)}%`
    : '—'
)

const num = (value, digits = 2) => (
  typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—'
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

  const targetSum = Object.values(targets).reduce((sum, value) => {
    const parsed = Number(value)
    return sum + (Number.isFinite(parsed) ? parsed : 0)
  }, 0)
  const sumInvalid = targetSum > 1.0 + 1e-9
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

  const saveTargets = async () => {
    setErr(''); setMsg('')
    if (sumInvalid) {
      setErr('target weights exceed 100%')
      return
    }
    try {
      const clean = Object.fromEntries(
        Object.entries(targets).map(([name, value]) => [name, Number(value) || 0])
      )
      await api.setRebalanceTargets({ targets: clean })
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

  const updateTarget = (name, raw) => {
    const next = Math.max(0, Number(raw) || 0) / 100
    setTargets((cur) => ({ ...cur, [name]: next }))
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
            <label>Drift %
              <input
                type="number"
                min="0"
                step="0.1"
                value={num((settings?.drift_threshold || 0) * 100, 1)}
                onChange={(e) => patchSettings({
                  drift_threshold: (Number(e.target.value) || 0) / 100,
                })}
              />
            </label>
            <label>Min interval
              <input
                type="number"
                min="0"
                step="1"
                value={settings?.min_interval_minutes ?? 0}
                onChange={(e) => patchSettings({
                  min_interval_minutes: Number(e.target.value) || 0,
                })}
              />
            </label>
            <label>Fee %
              <input
                type="number"
                min="0"
                step="0.01"
                value={num((settings?.fee_rate || 0) * 100, 2)}
                onChange={(e) => patchSettings({
                  fee_rate: (Number(e.target.value) || 0) / 100,
                })}
              />
            </label>
          </div>
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
                    <td>
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="0.1"
                        value={num(row.target * 100, 1)}
                        onChange={(e) => updateTarget(row.name, e.target.value)}
                      />
                    </td>
                    <td>{pct(row.actual)}</td>
                    <td className={row.drift >= 0 ? 'pos' : 'neg'}>{pct(row.drift)}</td>
                    <td><div className="drift-bar"><span style={{ width: `${Math.min(Math.abs(row.drift) * 100, 100)}%` }} /></div></td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          <div className={`row ${sumInvalid ? 'neg' : ''}`}>
            <span>Target sum</span><span>{pct(targetSum)}</span>
          </div>
          <button className="act" disabled={sumInvalid} onClick={saveTargets}>Save targets</button>
        </div>
      </div>
    </div>
  )
}
