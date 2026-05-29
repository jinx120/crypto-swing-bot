import { useEffect, useState } from 'react'
import { api } from '../api.js'
import TokenGate from '../components/TokenGate.jsx'

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
        <h3>Alpaca credentials</h3>
        {err && <div className="err">{err}</div>}{msg && <div className="pos">{msg}</div>}
        <div className="row"><span>Stored key</span><span>{st?.key_id ?? '—'}</span></div>
        <div className="row"><span>Secret set</span><span className={st?.has_secret?'pos':'neg'}>{String(!!st?.has_secret)}</span></div>
        <label>Key ID</label><input value={key} onChange={e=>setKey(e.target.value)} />
        <label>Secret key (write-only)</label><input type="password" value={sec} onChange={e=>setSec(e.target.value)} placeholder="••••••••" />
        <label><input type="checkbox" style={{width:'auto'}} checked={paper} onChange={e=>setPaper(e.target.checked)} /> Paper endpoint</label>
        <button className="act" style={{marginTop:10}} onClick={save}>Save credentials</button>
      </div>
      <TokenGate onSet={()=>load().catch(()=>{})} />
    </div>
  )
}
