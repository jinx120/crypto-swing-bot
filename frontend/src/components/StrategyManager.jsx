import { useEffect, useState } from 'react'
import { api } from '../api.js'
import Hint from './Hint.jsx'

export default function StrategyManager({ refreshKey }){
  const [rows, setRows] = useState([])
  const [settings, setSettings] = useState(null)
  const [err, setErr] = useState('')
  const load = async () => {
    try { setRows(await api.strategies()); setSettings(await api.portfolioSettings()); setErr('') }
    catch (e) { setErr(e.message) }
  }
  useEffect(() => { load() }, [refreshKey])
  const act = async (fn) => { setErr(''); try { await fn(); load() } catch (e) { setErr(e.message) } }
  const setS = (k) => (v) => setSettings(s => ({ ...s, [k]: v }))
  const saveSettings = () => act(() => api.setPortfolioSettings({
    max_concurrent: Number(settings.max_concurrent),
    max_total_deployed_frac: Number(settings.max_total_deployed_frac),
    portfolio_daily_loss_limit_pct: Number(settings.portfolio_daily_loss_limit_pct),
  }))
  return (
    <div className="panel full">
      <h3>Armed strategies
        <Hint text="Which strategies trade concurrently. Arm several (one per symbol). Live-eligible decides whether a strategy may open trades once the portfolio is in LIVE mode." />
      </h3>
      {err && <div className="err">{err}</div>}
      <table><thead><tr><th>Profile</th><th>Symbol</th><th>Armed</th><th>Live-eligible</th><th></th></tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.name}>
              <td>{r.name}</td><td>{r.symbol}</td>
              <td>{r.armed ? '✓' : '—'}</td>
              <td>{r.armed
                ? <input type="checkbox" style={{ width: 'auto' }} checked={r.live_eligible}
                    onChange={e => act(() => api.setLiveEligible(r.name, e.target.checked))} />
                : '—'}</td>
              <td>{r.armed
                ? <button className="act" onClick={() => act(() => api.disarm(r.name))}>Disarm</button>
                : <button className="act" onClick={() => act(() => api.arm(r.name))}>Arm</button>}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan="5">No profiles yet — create one below.</td></tr>}
        </tbody></table>

      {settings && <>
        <h3 style={{ marginTop: 16 }}>Portfolio caps
          <Hint text="Shared-pool safety limits applied across all strategies at once." />
        </h3>
        <label>Max concurrent positions<Hint text="Most positions open across the whole portfolio at once. A diversification/exposure cap, separate from how many you arm." /></label>
        <input type="number" value={settings.max_concurrent} onChange={e => setS('max_concurrent')(e.target.value)} />
        <label>Max total deployed (fraction of equity)<Hint text="Cap on the summed value of all open positions, e.g. 0.8 = 80% of equity. New entries that would breach it are skipped." /></label>
        <input type="number" step="0.01" value={settings.max_total_deployed_frac} onChange={e => setS('max_total_deployed_frac')(e.target.value)} />
        <label>Portfolio daily-loss kill switch<Hint text="If the whole portfolio's realized loss for the day reaches this fraction of equity, the portfolio kill switch trips and blocks all new entries." /></label>
        <input type="number" step="0.01" value={settings.portfolio_daily_loss_limit_pct} onChange={e => setS('portfolio_daily_loss_limit_pct')(e.target.value)} />
        <button className="act" style={{ marginTop: 12 }} onClick={saveSettings}>Save portfolio caps</button>
      </>}
    </div>
  )
}
