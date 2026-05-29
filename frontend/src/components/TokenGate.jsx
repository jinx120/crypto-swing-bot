import { useState } from 'react'
import { getToken, setToken } from '../api.js'

export default function TokenGate({ onSet }){
  const [t, setT] = useState(getToken())
  return (
    <div className="panel">
      <h3>API token</h3>
      <p style={{color:'var(--muted)'}}>Paste the token printed by <code>swingbot-web</code> on startup. Stored in this browser only.</p>
      <input value={t} onChange={e=>setT(e.target.value)} placeholder="token" />
      <button className="act" style={{marginTop:10}} onClick={()=>{ setToken(t); onSet?.() }}>Save token</button>
    </div>
  )
}
