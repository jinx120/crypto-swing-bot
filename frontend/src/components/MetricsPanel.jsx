export default function MetricsPanel({ metrics }){
  const m = metrics || {}
  const f = (x,d=2)=> (typeof x==='number' ? x.toFixed(d) : '—')
  return (
    <div className="panel full">
      <h3>Metrics</h3>
      <div className="row"><span>Expectancy / trade</span><span>{f(m.expectancy,4)}</span></div>
      <div className="row"><span>Win rate</span><span>{f((m.win_rate||0)*100,1)}%</span></div>
      <div className="row"><span>Profit factor</span><span>{f(m.profit_factor)}</span></div>
      <div className="row"><span>Max drawdown</span><span className="neg">{f(m.max_drawdown,2)}</span></div>
      <div className="row"><span>Trades</span><span>{m.n_trades ?? 0}</span></div>
    </div>
  )
}
