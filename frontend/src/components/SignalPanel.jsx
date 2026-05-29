export default function SignalPanel({ signal, symbol }){
  if (!signal) return <div className="panel"><h3>Signal</h3><div>—</div></div>
  if (signal.error) return <div className="panel"><h3>Signal</h3><div className="err">{signal.error}</div></div>
  const contrib = signal.contributions || {}
  return (
    <div className="panel">
      <h3>Signal — {symbol}</h3>
      {Object.entries(signal.signals || {}).map(([name, s])=>(
        <div className="row" key={name}>
          <span>{name}</span>
          <span>{(s.score ?? 0).toFixed(2)} → {(contrib[name] ?? 0).toFixed(3)}</span>
        </div>
      ))}
      <div className="row" style={{borderTop:'1px solid var(--line)',marginTop:6,paddingTop:6}}>
        <b>SCORE {(signal.score ?? 0).toFixed(3)} / {(signal.threshold ?? 0).toFixed(2)}</b>
        <span className={signal.passed?'pos':'neg'}>{signal.passed?'✓ would enter':'no'}</span>
      </div>
      <div className="row">Regime gate <span className={signal.permitted?'pos':'neg'}>{signal.permitted?'PASS':'VETO'}</span></div>
    </div>
  )
}
