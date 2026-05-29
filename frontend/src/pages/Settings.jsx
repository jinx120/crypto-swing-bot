import { useEffect, useState } from 'react'
import { api } from '../api.js'
import TokenGate from '../components/TokenGate.jsx'
import Hint from '../components/Hint.jsx'

export default function Settings(){
  const [st, setSt] = useState(null); const [err,setErr]=useState(''); const [msg,setMsg]=useState('')
  const [key, setKey] = useState(''); const [sec, setSec] = useState('')
  const [paper, setPaper] = useState(true)
  const load = async()=> setSt(await api.credStatus())
  useEffect(()=>{ load().catch(e=>setErr(e.message)) }, [])
  const save = async()=>{ setErr('');setMsg(''); try{
    const base = paper ? 'https://paper-api.alpaca.markets' : 'https://api.alpaca.markets'
    await api.setCreds(key, sec, base); setMsg('saved'); setSec(''); load()
  }catch(e){ setErr(e.message) } }
  return (
    <div className="wrap">
      <div className="panel">
        <h3>Alpaca credentials
          <Hint text="The API key pair from your Alpaca account that lets the bot read prices and place orders on your behalf. Create them in the Alpaca dashboard — paper and live each have their own keys." />
        </h3>
        {err && <div className="err">{err}</div>}{msg && <div className="pos">{msg}</div>}
        <div className="row"><span>Stored key
          <Hint text="The key ID currently saved on the server (the public half — safe to display)." /></span><span>{st?.key_id ?? '—'}</span></div>
        <div className="row"><span>Secret set
          <Hint text="Whether a secret key is on file. The secret itself is write-only — once saved it’s never shown back, only confirmed as set." /></span><span className={st?.has_secret?'pos':'neg'}>{String(!!st?.has_secret)}</span></div>
        <label>Key ID<Hint text="The public identifier of your Alpaca API key pair. Paste it from the Alpaca dashboard." /></label><input value={key} onChange={e=>setKey(e.target.value)} />
        <label>Secret key (write-only)<Hint text="The private half of the key pair — treat it like a password. It’s stored locally (file permissions locked down) and never sent back to this screen." /></label><input type="password" value={sec} onChange={e=>setSec(e.target.value)} placeholder="••••••••" />
        <label><input type="checkbox" style={{width:'auto'}} checked={paper} onChange={e=>setPaper(e.target.checked)} /> Paper endpoint<Hint text="Checked = connect to Alpaca’s paper (simulated) server with your paper keys. Uncheck only when you intend to trade real money with live keys." /></label>
        <button className="act" style={{marginTop:10}} onClick={save}>Save credentials</button>
      </div>
      <TokenGate onSet={()=>load().catch(()=>{})} />
    </div>
  )
}
