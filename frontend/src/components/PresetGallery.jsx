import { useEffect, useState } from 'react'
import { api } from '../api.js'
import Hint from './Hint.jsx'

const fmt = (x) => (x == null ? '—' : (+x).toFixed(2))
const pct = (x) => (x == null ? '—' : `${(+x * 100).toFixed(0)}%`)

export default function PresetGallery({ symbol, onUse }) {
  const [presets, setPresets] = useState([])
  const [coin, setCoin] = useState(symbol || '')
  const [results, setResults] = useState({})
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')

  useEffect(() => { api.presets().then(setPresets).catch(e => setErr(e.message)) }, [])

  const use = (p) => onUse({ ...p.profile, symbol: coin }, p.key)
  const test = async (p) => {
    setBusy(p.key); setErr('')
    try {
      const r = await api.backtestProfile({ ...p.profile, symbol: coin })
      setResults(s => ({ ...s, [p.key]: r.metrics }))
    } catch (e) { setResults(s => ({ ...s, [p.key]: { error: e.message } })) }
    finally { setBusy('') }
  }

  return (
    <div className="panel full">
      <h3>Preset strategies
        <Hint text="Ready-made strategies. Pick a coin, then Use to load one into the form below, or Backtest to see how it would have done on recent data." />
        <input className="coin-pick" value={coin} onChange={e => setCoin(e.target.value)} aria-label="coin" />
      </h3>
      {err && <div className="err">{err}</div>}
      <div className="preset-grid">
        {presets.map(p => (
          <div className="preset-card" key={p.key}>
            <div className="preset-name">{p.name}</div>
            <div className="preset-desc">{p.description}</div>
            <div className="preset-sig">{p.signals.join(' · ')}</div>
            {results[p.key] && (
              <div className="preset-metrics">
                {results[p.key].error
                  ? <span className="err">{results[p.key].error}</span>
                  : <>exp {fmt(results[p.key].expectancy)} · win {pct(results[p.key].win_rate)} · {results[p.key].n_trades} trades</>}
              </div>
            )}
            <div className="preset-actions">
              <button className="act" onClick={() => use(p)}>Use for {coin}</button>
              <button className="act" disabled={busy === p.key} onClick={() => test(p)}>
                {busy === p.key ? '…' : 'Backtest'}
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
