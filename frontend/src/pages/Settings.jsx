import { useEffect, useState } from 'react'
import { api } from '../api.js'
import TokenGate from '../components/TokenGate.jsx'
import Hint from '../components/Hint.jsx'
import RebalancePanel from '../components/RebalancePanel.jsx'

export default function Settings(){
  const [data, setData] = useState(null)       // { active, brokers: [...] }
  const [sel, setSel] = useState('')           // selected broker id
  const [vals, setVals] = useState({})         // field name -> input value
  const [mode, setMode] = useState('paper')
  const [err, setErr] = useState(''); const [msg, setMsg] = useState('')

  const load = async () => {
    const d = await api.listBrokers()
    setData(d)
    setSel(prev => prev || d.active)
  }
  useEffect(() => { load().catch(e => setErr(e.message)) }, [])
  useEffect(() => { setVals({}); setMsg(''); setErr('') }, [sel])

  if (!data) return <div className="wrap"><div className="panel">Loading…</div></div>
  const broker = data.brokers.find(b => b.id === sel) || data.brokers[0]

  const setField = (name, v) => setVals(s => ({ ...s, [name]: v }))

  const valuesPayload = () => {
    const out = { ...vals }
    if (broker.modes.includes('paper'))
      out.base_url = mode === 'paper'
        ? 'https://paper-api.alpaca.markets' : 'https://api.alpaca.markets'
    return out
  }

  const doTest = async () => { setErr(''); setMsg(''); try {
    const r = await api.testBroker(broker.id, valuesPayload(), mode)
    r.ok ? setMsg(`Test OK — ${r.detail}`) : setErr(`Test failed — ${r.detail}`)
  } catch (e) { setErr(e.message) } }

  const doSave = async () => { setErr(''); setMsg(''); try {
    await api.setBrokerCreds(broker.id, valuesPayload())
    if (data.active !== broker.id) await api.setActiveBroker(broker.id)
    setMsg('Saved'); setVals({}); load()
  } catch (e) { setErr(e.message) } }

  const doReconnect = async () => { setErr(''); setMsg(''); try {
    const r = await api.reconnectBroker()
    r.ok ? setMsg(`Reconnected — ${r.detail}`) : setErr(`Reconnect failed — ${r.detail}`)
  } catch (e) { setErr(e.message) } }

  return (
    <div className="wrap">
      <div className="panel">
        <h3>Broker connection
          <Hint text="The brokerage the bot trades through. Pick the active broker, paste its API keys, test the connection, then save. Reconnect applies new keys to the running bot without a restart." />
        </h3>
        {err && <div className="err">{err}</div>}{msg && <div className="pos">{msg}</div>}

        <label>Broker</label>
        <select value={sel} onChange={e => setSel(e.target.value)}>
          {data.brokers.map(b => (
            <option key={b.id} value={b.id}>
              {b.label}{b.id === data.active ? ' (active)' : ''}{b.configured ? ' ✓' : ''}
            </option>
          ))}
        </select>

        <div className="row"><span>Configured</span>
          <span className={broker.configured ? 'pos' : 'neg'}>{String(broker.configured)}</span></div>

        {broker.fields.map(f => (
          <div key={f.name}>
            <label>{f.label}{f.help && <Hint text={f.help} />}
              {broker.status.fields[f.name]?.set && !f.secret
                && <span className="muted"> (current: {broker.status.fields[f.name].value})</span>}
              {broker.status.fields[f.name]?.set && f.secret
                && <span className="pos"> (set)</span>}
            </label>
            <input
              type={f.secret ? 'password' : 'text'}
              value={vals[f.name] || ''}
              placeholder={f.secret ? '••••••••' : ''}
              onChange={e => setField(f.name, e.target.value)} />
          </div>
        ))}

        {broker.modes.includes('paper') && (
          <label><input type="checkbox" style={{ width: 'auto' }}
            checked={mode === 'paper'}
            onChange={e => setMode(e.target.checked ? 'paper' : 'live')} /> Paper endpoint
            <Hint text="Checked = simulated paper trading with your paper keys. Uncheck only to trade real money with live keys." />
          </label>
        )}

        <div style={{ marginTop: 10, display: 'flex', gap: 8 }}>
          <button className="act" onClick={doTest}>Test connection</button>
          <button className="act" onClick={doSave}>Save credentials</button>
          <button className="act" onClick={doReconnect}>Reconnect bot</button>
        </div>
      </div>
      <RebalancePanel />
      <TokenGate onSet={() => load().catch(() => {})} />
    </div>
  )
}
