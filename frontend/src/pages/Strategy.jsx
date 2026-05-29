import { useEffect, useState } from 'react'
import { api } from '../api.js'

const BLANK = {
  name: 'trx', symbol: 'TRX/USD', timeframe: '15m', benchmark_symbol: 'BTC/USD',
  entry_threshold: '0.3', regime_ma_period: '50',
  atr_period: '14', stop_atr_mult: '1.5', take_profit_atr_mult: '2.0', max_hold_bars: '32',
  risk_per_trade: '0.01', max_position_frac: '0.25',
  daily_loss_limit_pct: '0.05', max_consecutive_losses: '4', cooldown_minutes: '60',
  oversold_on: true, oversold_weight: '0.6', oversold_level: '45', oversold_period: '14',
  vwap_on: true, vwap_weight: '0.4', vwap_window: '96', vwap_max_dist: '0.03',
  rs_on: false, rs_weight: '0.3', rs_band: '0.02', rs_lookback: '96',
  fvg_on: false, fvg_weight: '0.0',
}

const g = (v, d) => (v === undefined || v === null ? d : String(v))

function parseProfile(name, p){
  const s = p.signals || {}
  const o = s.oversold || {}, v = s.vwap || {}, r = s.relative_strength || {}, fv = s.fvg || {}
  return {
    ...BLANK, name,
    symbol: g(p.symbol, BLANK.symbol), timeframe: g(p.timeframe, BLANK.timeframe),
    benchmark_symbol: g(p.benchmark_symbol, BLANK.benchmark_symbol),
    entry_threshold: g(p.entry_threshold, BLANK.entry_threshold),
    regime_ma_period: g(p.regime_ma_period, BLANK.regime_ma_period),
    atr_period: g(p.atr_period, BLANK.atr_period),
    stop_atr_mult: g(p.stop_atr_mult, BLANK.stop_atr_mult),
    take_profit_atr_mult: g(p.take_profit_atr_mult, BLANK.take_profit_atr_mult),
    max_hold_bars: g(p.max_hold_bars, BLANK.max_hold_bars),
    risk_per_trade: g(p.risk_per_trade, BLANK.risk_per_trade),
    max_position_frac: g(p.max_position_frac, BLANK.max_position_frac),
    daily_loss_limit_pct: g(p.daily_loss_limit_pct, BLANK.daily_loss_limit_pct),
    max_consecutive_losses: g(p.max_consecutive_losses, BLANK.max_consecutive_losses),
    cooldown_minutes: g(p.cooldown_minutes, BLANK.cooldown_minutes),
    oversold_on: !!s.oversold, oversold_weight: g(o.weight, BLANK.oversold_weight),
    oversold_level: g(o.oversold_level, BLANK.oversold_level), oversold_period: g(o.period, BLANK.oversold_period),
    vwap_on: !!s.vwap, vwap_weight: g(v.weight, BLANK.vwap_weight),
    vwap_window: g(v.window, BLANK.vwap_window), vwap_max_dist: g(v.max_dist, BLANK.vwap_max_dist),
    rs_on: !!s.relative_strength, rs_weight: g(r.weight, BLANK.rs_weight),
    rs_band: g(r.band, BLANK.rs_band), rs_lookback: g(r.lookback, BLANK.rs_lookback),
    fvg_on: !!s.fvg, fvg_weight: g(fv.weight, BLANK.fvg_weight),
  }
}

function assembleProfile(f){
  const n = (x) => Number(x)
  const signals = {}
  if (f.oversold_on) signals.oversold = { weight: n(f.oversold_weight), oversold_level: n(f.oversold_level), period: n(f.oversold_period) }
  if (f.vwap_on) signals.vwap = { weight: n(f.vwap_weight), window: n(f.vwap_window), max_dist: n(f.vwap_max_dist) }
  if (f.rs_on) signals.relative_strength = { weight: n(f.rs_weight), band: n(f.rs_band), lookback: n(f.rs_lookback) }
  if (f.fvg_on) signals.fvg = { weight: n(f.fvg_weight) }
  return {
    symbol: f.symbol, timeframe: f.timeframe, benchmark_symbol: f.benchmark_symbol,
    entry_threshold: n(f.entry_threshold), regime_ma_period: n(f.regime_ma_period),
    atr_period: n(f.atr_period), stop_atr_mult: n(f.stop_atr_mult),
    take_profit_atr_mult: n(f.take_profit_atr_mult), max_hold_bars: n(f.max_hold_bars),
    risk_per_trade: n(f.risk_per_trade), max_position_frac: n(f.max_position_frac),
    daily_loss_limit_pct: n(f.daily_loss_limit_pct),
    max_consecutive_losses: n(f.max_consecutive_losses), cooldown_minutes: n(f.cooldown_minutes),
    signals,
  }
}

function Num({ f, set, label, k, step = 'any' }){
  return (
    <div style={{ marginBottom: 8 }}>
      <label>{label}</label>
      <input type="number" step={step} value={f[k]} onChange={e => set(k)(e.target.value)} />
    </div>
  )
}
function Txt({ f, set, label, k }){
  return (
    <div style={{ marginBottom: 8 }}>
      <label>{label}</label>
      <input value={f[k]} onChange={e => set(k)(e.target.value)} />
    </div>
  )
}
function Toggle({ f, set, label, k }){
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text)', margin: '6px 0' }}>
      <input type="checkbox" style={{ width: 'auto' }} checked={f[k]} onChange={e => set(k)(e.target.checked)} /> {label}
    </label>
  )
}

export default function Strategy(){
  const [names, setNames] = useState([]); const [active, setActive] = useState(null)
  const [f, setF] = useState(BLANK)
  const [err, setErr] = useState(''); const [msg, setMsg] = useState('')
  const set = (k) => (val) => setF(prev => ({ ...prev, [k]: val }))

  const load = async () => { setNames(await api.listProfiles()); setActive((await api.activeProfile()).name) }
  useEffect(() => { load().catch(e => setErr(e.message)) }, [])

  const edit = async (name) => {
    setErr(''); setMsg('')
    try { const r = await api.getProfile(name); setF(parseProfile(name, r.profile)) }
    catch (e) { setErr(e.message) }
  }
  const newProfile = () => { setF(BLANK); setMsg('new blank profile'); setErr('') }
  const save = async () => {
    setErr(''); setMsg('')
    if (!f.oversold_on && !f.vwap_on && !f.rs_on && !f.fvg_on) { setErr('enable at least one signal'); return }
    try { await api.saveProfile(f.name, assembleProfile(f)); setMsg(`saved "${f.name}"`); load() }
    catch (e) { setErr(e.message) }
  }

  return (
    <div className="wrap">
      <div className="panel">
        <h3>Profiles</h3>
        {names.map(n => (
          <div className="row" key={n}>
            <span>{n} {active === n && <span className="chip">active</span>}</span>
            <span>
              <button className="act" onClick={() => edit(n)}>Edit</button>
              <button className="act" onClick={() => api.setActive(n).then(load).catch(e => setErr(e.message))}>Set active</button>
              <button className="act danger" onClick={() => api.deleteProfile(n).then(load)}>Delete</button>
            </span>
          </div>
        ))}
        {names.length === 0 && <div>No profiles yet — fill the form and Save →</div>}
        <button className="act" style={{ marginTop: 10 }} onClick={newProfile}>+ New blank</button>
      </div>

      <div className="panel">
        <h3>Strategy form</h3>
        {err && <div className="err">{err}</div>}{msg && <div className="pos">{msg}</div>}

        <Txt f={f} set={set} label="Profile name (save slot)" k="name" />
        <Txt f={f} set={set} label="Symbol (e.g. TRX/USD)" k="symbol" />
        <Txt f={f} set={set} label="Timeframe (e.g. 15m, 1h)" k="timeframe" />
        <Num f={f} set={set} label="Entry threshold (enter when total score ≥ this)" k="entry_threshold" />
        <Num f={f} set={set} label="Regime MA period (trend filter length)" k="regime_ma_period" />

        <h3 style={{ marginTop: 16 }}>Entry signals</h3>
        <p style={{ color: 'var(--muted)', marginTop: 0 }}>Each enabled signal adds score = its reading × weight. Weights usually sum to ~1.</p>

        <Toggle f={f} set={set} label="Oversold (RSI dip)" k="oversold_on" />
        {f.oversold_on && <div style={{ paddingLeft: 16 }}>
          <Num f={f} set={set} label="Weight" k="oversold_weight" /><Num f={f} set={set} label="Oversold level (RSI below this)" k="oversold_level" /><Num f={f} set={set} label="RSI period" k="oversold_period" />
        </div>}

        <Toggle f={f} set={set} label="VWAP (price below fair value)" k="vwap_on" />
        {f.vwap_on && <div style={{ paddingLeft: 16 }}>
          <Num f={f} set={set} label="Weight" k="vwap_weight" /><Num f={f} set={set} label="VWAP window (bars)" k="vwap_window" /><Num f={f} set={set} label="Max distance below VWAP (e.g. 0.03 = 3%)" k="vwap_max_dist" />
        </div>}

        <Toggle f={f} set={set} label="Relative strength (vs benchmark)" k="rs_on" />
        {f.rs_on && <div style={{ paddingLeft: 16 }}>
          <Txt f={f} set={set} label="Benchmark symbol" k="benchmark_symbol" /><Num f={f} set={set} label="Weight" k="rs_weight" /><Num f={f} set={set} label="Band (sensitivity, e.g. 0.02)" k="rs_band" /><Num f={f} set={set} label="Lookback (bars)" k="rs_lookback" />
        </div>}

        <Toggle f={f} set={set} label="Fair Value Gap (not implemented yet — scores 0)" k="fvg_on" />
        {f.fvg_on && <div style={{ paddingLeft: 16 }}><Num f={f} set={set} label="Weight" k="fvg_weight" /></div>}

        <h3 style={{ marginTop: 16 }}>Exits</h3>
        <Num f={f} set={set} label="ATR period" k="atr_period" />
        <Num f={f} set={set} label="Stop = entry − (this × ATR)" k="stop_atr_mult" />
        <Num f={f} set={set} label="Take-profit = entry + (this × ATR)" k="take_profit_atr_mult" />
        <Num f={f} set={set} label="Max hold (bars) before time-exit" k="max_hold_bars" />

        <h3 style={{ marginTop: 16 }}>Risk & circuit breakers</h3>
        <Num f={f} set={set} label="Risk per trade (fraction of equity, e.g. 0.01 = 1%)" k="risk_per_trade" />
        <Num f={f} set={set} label="Max position size (fraction of equity)" k="max_position_frac" />
        <Num f={f} set={set} label="Daily loss kill-switch (e.g. 0.05 = −5%)" k="daily_loss_limit_pct" />
        <Num f={f} set={set} label="Max consecutive losses before halt" k="max_consecutive_losses" />
        <Num f={f} set={set} label="Cooldown after a stop-out (minutes)" k="cooldown_minutes" />

        <button className="act" style={{ marginTop: 14 }} onClick={save}>Save profile</button>
      </div>
    </div>
  )
}
