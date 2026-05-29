import { useEffect, useState } from 'react'
import { api } from '../api.js'

const DEFAULT = {
  symbol: 'TRX/USD', timeframe: '15m', entry_threshold: 0.3, regime_ma_period: 50,
  atr_period: 14, stop_atr_mult: 1.5, take_profit_atr_mult: 2.0, max_hold_bars: 32,
  risk_per_trade: 0.01, max_position_frac: 0.25,
  daily_loss_limit_pct: 0.05, max_consecutive_losses: 4, cooldown_minutes: 60,
  signals: { oversold: { weight: 0.6, oversold_level: 45, period: 14 },
             vwap: { weight: 0.4, window: 96, max_dist: 0.03 } },
}

export default function Strategy(){
  const [names, setNames] = useState([]); const [active, setActive] = useState(null)
  const [name, setName] = useState('trx'); const [json, setJson] = useState(JSON.stringify(DEFAULT, null, 2))
  const [err, setErr] = useState(''); const [msg, setMsg] = useState('')
  const load = async()=>{ setNames(await api.listProfiles()); const a = await api.activeProfile(); setActive(a.name) }
  useEffect(()=>{ load().catch(e=>setErr(e.message)) }, [])
  const save = async()=>{ setErr(''); setMsg(''); try{ await api.saveProfile(name, JSON.parse(json)); setMsg('saved'); load() }catch(e){ setErr(e.message) } }
  return (
    <div className="wrap">
      <div className="panel">
        <h3>Profiles</h3>
        {names.map(n=> <div className="row" key={n}>
          <span>{n} {active===n && <span className="chip">active</span>}</span>
          <span>
            <button className="act" onClick={()=>api.setActive(n).then(load).catch(e=>setErr(e.message))}>Set active</button>
            <button className="act danger" onClick={()=>api.deleteProfile(n).then(load)}>Delete</button>
          </span>
        </div>)}
        {names.length===0 && <div>No profiles yet — create one →</div>}
      </div>
      <div className="panel">
        <h3>Create / edit profile</h3>
        {err && <div className="err">{err}</div>}{msg && <div className="pos">{msg}</div>}
        <label>Name</label><input value={name} onChange={e=>setName(e.target.value)} />
        <label>Profile JSON (form-free editor)</label>
        <textarea style={{width:'100%',height:320,fontFamily:'monospace',background:'#0c1320',color:'var(--text)',border:'1px solid var(--line)',borderRadius:6,padding:8}}
          value={json} onChange={e=>setJson(e.target.value)} />
        <button className="act" style={{marginTop:10}} onClick={save}>Save profile</button>
      </div>
    </div>
  )
}
