import { useState } from 'react'
import { api } from '../api.js'
import Hint from './Hint.jsx'

const RISKS = ['conservative', 'balanced', 'aggressive']
const STYLES = ['scalp', 'swing', 'position']
const fmt = (x) => (x == null ? '—' : (+x).toFixed(2))
const pct = (x) => (x == null ? '—' : `${(+x * 100).toFixed(0)}%`)

export default function StrategyBuilder({ symbol, onUse }) {
  const [coin, setCoin] = useState(symbol || 'TRX/USD')
  const [risk, setRisk] = useState('balanced')
  const [style, setStyle] = useState('swing')
  const [ai, setAi] = useState(false)
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState(null)
  const [err, setErr] = useState('')

  const build = async () => {
    setBusy(true); setErr(''); setRes(null)
    try { setRes(await api.buildStrategy({ symbol: coin, risk, style, ai })) }
    catch (e) { setErr(e.message) }
    finally { setBusy(false) }
  }

  return (
    <div className="panel full">
      <h3>Guided builder
        <Hint text="Pick a coin and your preferences; the server backtests several candidate strategies on recent data and recommends the best. Use a row to load it into the form below." />
      </h3>
      <div className="builder-row">
        <label>Coin<input value={coin} onChange={e => setCoin(e.target.value)} /></label>
        <label>Risk<select value={risk} onChange={e => setRisk(e.target.value)}>
          {RISKS.map(r => <option key={r} value={r}>{r}</option>)}</select></label>
        <label>Style<select value={style} onChange={e => setStyle(e.target.value)}>
          {STYLES.map(s => <option key={s} value={s}>{s}</option>)}</select></label>
        <label className="builder-ai">
          <input type="checkbox" checked={ai} onChange={e => setAi(e.target.checked)} /> Use AI (Kronos)
        </label>
        <button className="act" disabled={busy} onClick={build}>{busy ? 'Searching…' : 'Build & backtest'}</button>
      </div>
      {ai && <p style={{ color: 'var(--muted)', marginTop: 0 }}>AI search is slower — runs fewer candidates.</p>}
      {err && <div className="err">{err}</div>}
      {res && (
        <table>
          <thead><tr><th></th><th>Strategy</th><th>Expectancy</th><th>Win%</th><th>Trades</th><th></th></tr></thead>
          <tbody>
            {res.results.map((r, i) => (
              <tr key={i} className={r.recommended ? 'rec' : ''}>
                <td>{r.recommended ? '★' : ''}</td>
                <td>{r.label}</td>
                <td>{r.error ? <span className="err">{r.error}</span> : fmt(r.metrics.expectancy)}</td>
                <td>{r.error ? '—' : pct(r.metrics.win_rate)}</td>
                <td>{r.error ? '—' : r.metrics.n_trades}</td>
                <td>{!r.error && <button className="act" onClick={() => onUse(r.profile)}>Use this</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
