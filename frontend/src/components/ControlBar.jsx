import { useState } from 'react'
import { api } from '../api.js'

export default function ControlBar({ state, onChange }){
  const [err, setErr] = useState('')
  const run = async (fn) => { setErr(''); try { await fn(); onChange?.() } catch(e){ setErr(e.message) } }
  const confirmRun = (msg, fn) => { if (window.confirm(msg)) run(fn) }
  const paused = state?.paused
  return (
    <div className="panel full">
      <h3>Controls</h3>
      {err && <div className="err">{err}</div>}
      <button className="act danger" onClick={()=>confirmRun('Trip the kill switch (stop new entries)?', ()=>api.control('halt'))}>HALT</button>
      <button className="act" onClick={()=>run(()=>api.control('reset'))}>Reset kill switch</button>
      {paused
        ? <button className="act" onClick={()=>run(()=>api.control('resume'))}>Resume</button>
        : <button className="act" onClick={()=>run(()=>api.control('pause'))}>Pause entries</button>}
      <button className="act danger" onClick={()=>confirmRun('Flatten (market-sell) the open position now?', ()=>api.control('flatten'))}>Flatten</button>
      <button className="act danger" onClick={()=>confirmRun('Switch to LIVE (real money)? Server will block if not graduated.', async()=>{
        const r = await api.control('mode', { mode: 'live' }); if(!r.ok) throw new Error(r.reason)
      })}>Go LIVE</button>
      <button className="act" onClick={()=>run(async()=>{ const r=await api.control('mode',{mode:'paper'}); if(!r.ok) throw new Error(r.reason) })}>Go paper</button>
    </div>
  )
}
