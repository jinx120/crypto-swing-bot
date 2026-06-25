import { useEffect, useState } from 'react'
import { api } from '../../api.js'
import { Card, CardContent } from '../ui/card.jsx'
import { Button } from '../ui/button.jsx'
import { Switch } from '../ui/switch.jsx'
import { buildProfilePatch } from '../../lib/derive.js'

const REGIME_ON = ['uptrend', 'neutral']
const REGIME_OFF = ['uptrend', 'neutral', 'downtrend']
const NUMERIC = [
  ['entry_threshold', 'Entry threshold'],
  ['tp_pct', 'Take-profit %'],
  ['sl_pct', 'Stop-loss %'],
  ['stop_atr_mult', 'Stop ATRx'],
  ['take_profit_atr_mult', 'TP ATRx'],
  ['max_hold_bars', 'Max hold (bars)'],
  ['risk_per_trade', 'Risk per trade'],
  ['max_position_frac', 'Max position frac'],
  ['daily_loss_limit_pct', 'Daily loss limit'],
  ['max_consecutive_losses', 'Max consecutive losses'],
]

export default function GatesParametersPanel({ name }) {
  const [profile, setProfile] = useState(null)
  const [draft, setDraft] = useState(null)
  const [open, setOpen] = useState(false)
  const [msg, setMsg] = useState('')
  const [err, setErr] = useState('')

  const load = async () => {
    try {
      const r = await api.getStrategyProfile(name)
      setProfile(r.profile)
      setDraft(JSON.parse(JSON.stringify(r.profile)))
    } catch (e) {
      setErr(e.message)
    }
  }
  useEffect(() => { load() /* eslint-disable-next-line */ }, [name])

  if (!draft) return null
  const regimeOn = !(draft.allowed_regimes || REGIME_ON).includes('downtrend')
  const signals = draft.signals || {}

  const setNum = (k, v) => setDraft({ ...draft, [k]: v === '' ? '' : Number(v) })
  const setSignalGate = (sig, on) =>
    setDraft({ ...draft, signals: { ...signals, [sig]: { ...signals[sig], gate: on } } })
  const setSignalMin = (sig, v) =>
    setDraft({ ...draft, signals: { ...signals, [sig]: { ...signals[sig], min_score: Number(v) } } })

  const save = async () => {
    setErr('')
    setMsg('')
    const edits = { ...draft }
    edits.allowed_regimes = regimeOn ? REGIME_ON : REGIME_OFF
    const patch = buildProfilePatch(profile, edits)
    if (Object.keys(patch).length === 0) {
      setMsg('no changes')
      return
    }
    try {
      const r = await api.updateStrategyProfile(name, patch)
      setProfile(r.profile)
      setMsg('saved, live — no rebuild')
    } catch (e) {
      setErr(e.message)
    }
  }

  return (
    <Card>
      <CardContent className="p-4">
        <button className="flex w-full items-center justify-between text-sm font-semibold"
          onClick={() => setOpen(!open)}>
          <span>Gates &amp; Parameters</span>
          <span className="text-muted-foreground">{open ? 'v' : '>'}</span>
        </button>
        {open && (
          <div className="mt-3 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm">Regime gate</div>
                <div className="text-xs text-muted-foreground">
                  ON blocks entries during a 4h downtrend; OFF permits any regime.
                </div>
              </div>
              <Switch checked={regimeOn}
                onCheckedChange={(on) => setDraft({
                  ...draft, allowed_regimes: on ? REGIME_ON : REGIME_OFF,
                })} />
            </div>

            <div className="space-y-2">
              <div className="text-xs font-semibold text-muted-foreground">Signal gates</div>
              {Object.keys(signals).map((sig) => (
                <div key={sig} className="flex items-center gap-3 text-sm">
                  <span className="w-32 font-mono">{sig}</span>
                  <Switch checked={!!signals[sig].gate}
                    onCheckedChange={(on) => setSignalGate(sig, on)} />
                  <span className="text-xs text-muted-foreground">gate</span>
                  <input type="number" step="0.05" className="ml-auto w-20 rounded border bg-background px-2 py-1 text-right"
                    value={signals[sig].min_score ?? 0}
                    onChange={(e) => setSignalMin(sig, e.target.value)} />
                  <span className="text-xs text-muted-foreground">min score</span>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-2">
              {NUMERIC.filter(([k]) => draft[k] !== undefined).map(([k, label]) => (
                <label key={k} className="text-xs">
                  <span className="text-muted-foreground">{label}</span>
                  <input type="number" step="any"
                    className="mt-1 w-full rounded border bg-background px-2 py-1"
                    value={draft[k]} onChange={(e) => setNum(k, e.target.value)} />
                </label>
              ))}
            </div>

            {err && <div className="text-xs text-down">{err}</div>}
            {msg && <div className="text-xs text-up">{msg}</div>}
            <div className="flex justify-end">
              <Button size="sm" onClick={save}>Save</Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
