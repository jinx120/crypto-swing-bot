import Hint from './Hint.jsx'

export default function MetricsPanel({ metrics }){
  const m = metrics || {}
  const f = (x,d=2)=> (typeof x==='number' ? x.toFixed(d) : '—')
  return (
    <div className="panel full">
      <h3>Metrics
        <Hint text="Performance of all closed trades so far. With only a handful of trades these numbers are noisy — judge the strategy over many trades, not a few." />
      </h3>
      <div className="row"><span>Expectancy / trade
        <Hint text="Average profit (or loss) you can expect per trade, in account currency. Above zero means the strategy makes money on average — the single most important number here." /></span><span>{f(m.expectancy,4)}</span></div>
      <div className="row"><span>Win rate
        <Hint text="Share of trades that closed in profit. A low win rate can still be very profitable if the winners are much bigger than the losers." /></span><span>{f((m.win_rate||0)*100,1)}%</span></div>
      <div className="row"><span>Profit factor
        <Hint text="Total profit from winners ÷ total loss from losers. Above 1.0 = profitable; around 2.0 is strong." /></span><span>{f(m.profit_factor)}</span></div>
      <div className="row"><span>Max drawdown
        <Hint text="The largest peak-to-trough drop in account value over this history — the worst losing stretch you’d have had to sit through. Smaller is better." /></span><span className="neg">{f(m.max_drawdown,2)}</span></div>
      <div className="row"><span>Trades
        <Hint text="Number of completed (closed) trades behind these stats. More trades = more trustworthy numbers." /></span><span>{m.n_trades ?? 0}</span></div>
    </div>
  )
}
