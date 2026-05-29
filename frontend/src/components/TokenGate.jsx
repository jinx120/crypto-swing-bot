import { useState } from 'react'
import { getToken, setToken } from '../api.js'
import Hint from './Hint.jsx'

export default function TokenGate({ onSet }){
  const [t, setT] = useState(getToken())
  return (
    <div className="panel">
      <h3>API token
        <Hint text="A password that authorizes control actions (HALT, Flatten, Go LIVE, saving settings). The server prints it when you start swingbot-web; paste it here so this browser is trusted. It’s stored only in this browser." />
      </h3>
      <p style={{color:'var(--muted)'}}>Paste the token printed by <code>swingbot-web</code> on startup. Stored in this browser only.</p>
      <input value={t} onChange={e=>setT(e.target.value)} placeholder="token" />
      <button className="act" style={{marginTop:10}} onClick={()=>{ setToken(t); onSet?.() }}>Save token</button>
    </div>
  )
}
