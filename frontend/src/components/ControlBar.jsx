import { useState } from 'react'
import { api } from '../api.js'
import Hint from './Hint.jsx'

export default function ControlBar({ state, onChange }){
  const [err, setErr] = useState('')
  const run = async (fn) => { setErr(''); try { await fn(); onChange?.() } catch(e){ setErr(e.message) } }
  const confirmRun = (msg, fn) => { if (window.confirm(msg)) run(fn) }
  const paused = state?.paused
  return (
    <div className="panel full">
      <h3>Controls
        <Hint text="Manual overrides. The bot runs on its own — use these only when you want to step in." />
      </h3>
      {err && <div className="err">{err}</div>}
      <button className="act danger" onClick={()=>confirmRun('Trip the kill switch (stop new entries)?', ()=>api.control('halt'))}>HALT</button>
      <Hint text="Trips the kill switch right away: no new trades. Open positions keep being managed by their stop/target — HALT does not sell them." />
      <button className="act" onClick={()=>run(()=>api.control('reset'))}>Reset kill switch</button>
      <Hint text="Clears a tripped kill switch so the bot can take new entries again. Use once you’ve checked what tripped it." />
      {paused
        ? <button className="act" onClick={()=>run(()=>api.control('resume'))}>Resume</button>
        : <button className="act" onClick={()=>run(()=>api.control('pause'))}>Pause entries</button>}
      <Hint text="Pause = stop scanning for new trades but keep the bot running and managing open ones. Lighter and more easily reversed than HALT. Resume turns scanning back on." />
      <button className="act danger" onClick={()=>confirmRun('Flatten (market-sell) the open position now?', ()=>api.control('flatten'))}>Flatten</button>
      <Hint text="Immediately market-sells the open position, ignoring the stop and target. Use when you want out right now." />
      <button className="act danger" onClick={()=>confirmRun('Switch to LIVE (real money)? Server will block if not graduated.', async()=>{
        const r = await api.control('mode', { mode: 'live' }); if(!r.ok) throw new Error(r.reason)
      })}>Go LIVE</button>
      <Hint text="Switches to trading real money. The server refuses unless your paper results have passed the graduation checks — a deliberate guardrail." />
      <button className="act" onClick={()=>run(async()=>{ const r=await api.control('mode',{mode:'paper'}); if(!r.ok) throw new Error(r.reason) })}>Go paper</button>
      <Hint text="Switches back to simulated (paper) money. Always safe to do." />
    </div>
  )
}
