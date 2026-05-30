import { useEffect, useState } from 'react'
import { api } from '../api.js'
import Hint from '../components/Hint.jsx'

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
  kronos_on: false, kronos_weight: '0.25', kronos_pred_len: '4', kronos_threshold_pct: '0.02',
}

const g = (v, d) => (v === undefined || v === null ? d : String(v))

function parseProfile(name, p){
  const s = p.signals || {}
  const o = s.oversold || {}, v = s.vwap || {}, r = s.relative_strength || {},
        fv = s.fvg || {}, kn = s.kronos_forecast || {}
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
    kronos_on: !!s.kronos_forecast,
    kronos_weight: g(kn.weight, BLANK.kronos_weight),
    kronos_pred_len: g(kn.pred_len, BLANK.kronos_pred_len),
    kronos_threshold_pct: g(kn.threshold_pct, BLANK.kronos_threshold_pct),
  }
}

function assembleProfile(f){
  const n = (x) => Number(x)
  const signals = {}
  if (f.oversold_on) signals.oversold = { weight: n(f.oversold_weight), oversold_level: n(f.oversold_level), period: n(f.oversold_period) }
  if (f.vwap_on) signals.vwap = { weight: n(f.vwap_weight), window: n(f.vwap_window), max_dist: n(f.vwap_max_dist) }
  if (f.rs_on) signals.relative_strength = { weight: n(f.rs_weight), band: n(f.rs_band), lookback: n(f.rs_lookback) }
  if (f.fvg_on) signals.fvg = { weight: n(f.fvg_weight) }
  if (f.kronos_on) signals.kronos_forecast = {
    weight: n(f.kronos_weight),
    pred_len: n(f.kronos_pred_len),
    threshold_pct: n(f.kronos_threshold_pct),
  }
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

function Num({ f, set, label, k, step = 'any', hint }){
  return (
    <div style={{ marginBottom: 8 }}>
      <label>{label}{hint && <Hint text={hint} />}</label>
      <input type="number" step={step} value={f[k]} onChange={e => set(k)(e.target.value)} />
    </div>
  )
}
function Txt({ f, set, label, k, hint }){
  return (
    <div style={{ marginBottom: 8 }}>
      <label>{label}{hint && <Hint text={hint} />}</label>
      <input value={f[k]} onChange={e => set(k)(e.target.value)} />
    </div>
  )
}
function Toggle({ f, set, label, k, hint }){
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text)', margin: '6px 0' }}>
      <input type="checkbox" style={{ width: 'auto' }} checked={f[k]} onChange={e => set(k)(e.target.checked)} /> {label}
      {hint && <Hint text={hint} />}
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
    if (!f.oversold_on && !f.vwap_on && !f.rs_on && !f.fvg_on && !f.kronos_on) { setErr('enable at least one signal'); return }
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

        <Txt f={f} set={set} label="Profile name (save slot)" k="name"
          hint="A label for this saved configuration. Keep one per coin or per idea, then pick which is active." />
        <Txt f={f} set={set} label="Symbol (e.g. TRX/USD)" k="symbol"
          hint="The Alpaca crypto pair to trade. Must be a pair Alpaca supports for spot trading, written BASE/QUOTE." />
        <Txt f={f} set={set} label="Timeframe (e.g. 15m, 1h)" k="timeframe"
          hint="The candle size the bot works on. Each ‘bar’ is one candle, so 15m means it re-evaluates every 15 minutes and most settings below are counted in these bars." />
        <Num f={f} set={set} label="Entry threshold (enter when total score ≥ this)" k="entry_threshold"
          hint="The minimum confluence score needed to buy. Higher = pickier (fewer, higher-conviction trades); lower = more trades. Tune it against the weights of your enabled signals." />
        <Num f={f} set={set} label="Regime MA period (trend filter length)" k="regime_ma_period"
          hint="Length (in bars) of the moving average used as the trend filter. Price above it = uptrend, so entries are allowed; below it = downtrend, so entries are blocked. Longer = slower, smoother trend." />

        <h3 style={{ marginTop: 16 }}>Entry signals
          <Hint text="The buy triggers. Turn on the ones you trust; each contributes its reading × weight to the total score. The bot buys when the combined score clears the entry threshold and the trend gate allows it." />
        </h3>
        <p style={{ color: 'var(--muted)', marginTop: 0 }}>Each enabled signal adds score = its reading × weight. Weights usually sum to ~1.</p>

        <Toggle f={f} set={set} label="Oversold (RSI dip)" k="oversold_on"
          hint="RSI measures recent momentum on a 0–100 scale. A low reading means the coin just sold off hard (‘oversold’) — a classic buy-the-dip trigger." />
        {f.oversold_on && <div style={{ paddingLeft: 16 }}>
          <Num f={f} set={set} label="Weight" k="oversold_weight"
            hint="How much this signal counts toward the total score, relative to your other enabled signals." /><Num f={f} set={set} label="Oversold level (RSI below this)" k="oversold_level"
            hint="The RSI value the price must drop under to count as oversold. Lower (e.g. 30) = waits for a deeper dip; higher (e.g. 45) = fires more often." /><Num f={f} set={set} label="RSI period" k="oversold_period"
            hint="How many bars the RSI looks back over. 14 is the standard. Shorter reacts faster but is noisier." />
        </div>}

        <Toggle f={f} set={set} label="VWAP (price below fair value)" k="vwap_on"
          hint="VWAP = Volume-Weighted Average Price, a running ‘fair value’ that weights price by how much traded there. Buying below it aims to get in at a discount to where most volume changed hands." />
        {f.vwap_on && <div style={{ paddingLeft: 16 }}>
          <Num f={f} set={set} label="Weight" k="vwap_weight"
            hint="How much this signal counts toward the total score, relative to your other enabled signals." /><Num f={f} set={set} label="VWAP window (bars)" k="vwap_window"
            hint="How many bars the VWAP is averaged over. Larger = a slower, longer-term fair-value reference." /><Num f={f} set={set} label="Max distance below VWAP (e.g. 0.03 = 3%)" k="vwap_max_dist"
            hint="How far below VWAP still counts as a good buy. Price more than this far under VWAP is treated as ‘too far gone’ rather than a discount." />
        </div>}

        <Toggle f={f} set={set} label="Relative strength (vs benchmark)" k="rs_on"
          hint="Compares this coin’s recent move against a benchmark like BTC. It favors coins holding up better than the broader market — another defense against picking a coin that’s quietly bleeding out." />
        {f.rs_on && <div style={{ paddingLeft: 16 }}>
          <Txt f={f} set={set} label="Benchmark symbol" k="benchmark_symbol"
            hint="The pair to measure relative strength against — usually a market bellwether like BTC/USD." /><Num f={f} set={set} label="Weight" k="rs_weight"
            hint="How much this signal counts toward the total score, relative to your other enabled signals." /><Num f={f} set={set} label="Band (sensitivity, e.g. 0.02)" k="rs_band"
            hint="How much the coin must out- or under-perform the benchmark before it moves the score. Smaller = more sensitive." /><Num f={f} set={set} label="Lookback (bars)" k="rs_lookback"
            hint="How many bars back to compare performance over." />
        </div>}

        <Toggle f={f} set={set} label="Fair Value Gap (not implemented yet — scores 0)" k="fvg_on"
          hint="A Fair Value Gap is a price imbalance left by a fast move that the market often returns to fill. It’s a placeholder here — not built yet, so it always scores 0 and won’t affect entries." />
        {f.fvg_on && <div style={{ paddingLeft: 16 }}><Num f={f} set={set} label="Weight" k="fvg_weight"
          hint="Has no effect until this signal is implemented." /></div>}

        <Toggle f={f} set={set} label="Kronos Forecast (AI time-series model)" k="kronos_on"
          hint="Kronos is a foundation model for time-series that forecasts future OHLCV bars. Requires ‘pip install -e .[kronos]’ on the server where the bot runs. When disabled, this signal is not loaded and torch is not required." />
        {f.kronos_on && <div style={{ paddingLeft: 16 }}>
          <Num f={f} set={set} label="Weight" k="kronos_weight" step="0.01"
            hint="Contribution to the confluence score. 0.25 = 25% weight. Tune alongside your other enabled signals." />
          <Num f={f} set={set} label="Forecast bars (pred_len)" k="kronos_pred_len" step="1"
            hint="How many bars ahead Kronos forecasts. At 15m timeframe, 4 bars = 1 hour ahead. Higher gives a longer-horizon view but is less precise." />
          <Num f={f} set={set} label="Bullish threshold %" k="kronos_threshold_pct" step="0.001"
            hint="The expected % gain that maps to score 1.0. E.g. 0.02 means a 2% forecast gain = maximum score. Flat or negative forecasts always score 0." />
        </div>}

        <h3 style={{ marginTop: 16 }}>Exits
          <Hint text="How each trade is closed. Alpaca crypto can’t hold stop/target orders on the exchange, so the bot enforces these itself on every bar — they’re always on." />
        </h3>
        <Num f={f} set={set} label="ATR period" k="atr_period"
          hint="ATR (Average True Range) measures how much the coin typically moves per bar — its recent volatility. Sizing stops and targets in ATR makes them adapt: wider when the coin is wild, tighter when it’s calm." />
        <Num f={f} set={set} label="Stop = entry − (this × ATR)" k="stop_atr_mult"
          hint="How far below entry to place the stop-loss, in ATRs. Larger = more breathing room but a bigger loss if hit. 1.5 means stop = entry − 1.5 × ATR." />
        <Num f={f} set={set} label="Take-profit = entry + (this × ATR)" k="take_profit_atr_mult"
          hint="How far above entry to place the profit target, in ATRs. Set it larger than the stop multiple to aim for winners bigger than losers." />
        <Num f={f} set={set} label="Max hold (bars) before time-exit" k="max_hold_bars"
          hint="If neither stop nor target hits, the bot closes the trade after this many bars so capital isn’t stuck in a position going nowhere. This is a swing bot, not a hodl bot." />

        <h3 style={{ marginTop: 16 }}>Risk &amp; circuit breakers
          <Hint text="The guardrails that keep one bad trade — or one bad day — from doing real damage. These run automatically." />
        </h3>
        <Num f={f} set={set} label="Risk per trade (fraction of equity, e.g. 0.01 = 1%)" k="risk_per_trade"
          hint="How much of your account you’re willing to lose if the stop is hit. The bot sizes each position from this and the stop distance. 1% per trade is a common conservative choice." />
        <Num f={f} set={set} label="Max position size (fraction of equity)" k="max_position_frac"
          hint="A hard cap on how big any single position can get, as a fraction of your account — a backstop in case a tight stop would otherwise call for an oversized buy." />
        <Num f={f} set={set} label="Daily loss kill-switch (e.g. 0.05 = −5%)" k="daily_loss_limit_pct"
          hint="If the day’s losses reach this fraction of your account, the kill switch trips and the bot stops opening new trades for the day. Your circuit breaker against a bad session." />
        <Num f={f} set={set} label="Max consecutive losses before halt" k="max_consecutive_losses"
          hint="Trips the kill switch after this many losing trades in a row — a sign the strategy is out of sync with the market, so it steps aside." />
        <Num f={f} set={set} label="Cooldown after a stop-out (minutes)" k="cooldown_minutes"
          hint="After getting stopped out, the bot waits this long before considering a new entry — avoids instantly re-buying into the same drop." />

        <button className="act" style={{ marginTop: 14 }} onClick={save}>Save profile</button>
      </div>
    </div>
  )
}
