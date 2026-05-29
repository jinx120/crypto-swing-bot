import Hint from './Hint.jsx'

export default function SignalPanel({ signal, symbol }){
  if (!signal) return <div className="panel"><h3>Signal</h3><div>—</div></div>
  if (signal.error) return <div className="panel"><h3>Signal</h3><div className="err">{signal.error}</div></div>
  const contrib = signal.contributions || {}
  return (
    <div className="panel">
      <h3>Signal — {symbol}
        <Hint text="The bot blends several independent buy signals into one “confluence” score. More signals agreeing = higher score. It only enters when the score clears your threshold AND the trend (regime) gate allows it." />
      </h3>
      {Object.entries(signal.signals || {}).map(([name, s])=>(
        <div className="row" key={name}>
          <span>{name}
            {name === Object.keys(signal.signals||{})[0] &&
              <Hint text="Left number = this signal’s raw reading right now (0–1, higher = stronger buy case). Right number = that reading multiplied by the signal’s weight — its actual contribution to the total score." />}
          </span>
          <span>{(s.score ?? 0).toFixed(2)} → {(contrib[name] ?? 0).toFixed(3)}</span>
        </div>
      ))}
      <div className="row" style={{borderTop:'1px solid var(--line)',marginTop:6,paddingTop:6}}>
        <b>SCORE {(signal.score ?? 0).toFixed(3)} / {(signal.threshold ?? 0).toFixed(2)}
          <Hint text="Sum of every signal’s contribution, shown against your entry threshold. “Would enter” means the score is high enough — but a trade still only happens if the regime gate also passes." />
        </b>
        <span className={signal.passed?'pos':'neg'}>{signal.passed?'✓ would enter':'no'}</span>
      </div>
      <div className="row"><span>Regime gate
        <Hint text="A hard trend filter applied on top of the score. VETO blocks all new entries — even a perfect score won’t trade in a downtrend." /></span>
        <span className={signal.permitted?'pos':'neg'}>{signal.permitted?'PASS':'VETO'}</span>
      </div>
    </div>
  )
}
