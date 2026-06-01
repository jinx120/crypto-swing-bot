import Hint from './Hint.jsx'

export default function PortfolioBanner({ portfolio }){
  const p = portfolio || {}
  const halted = p.kill_switch?.active
  const pnl = p.day_pnl ?? 0
  const f = (x, d = 2) => (typeof x === 'number' ? x.toFixed(d) : '—')
  return (
    <div className={`banner ${halted ? 'halted' : ''}`}>
      <span>Mode: <b>{(p.mode || 'paper').toUpperCase()}</b>
        <Hint text="Whole-portfolio money mode. PAPER = simulated; LIVE = real money (gated)." />
      </span>
      <span>Equity: <b>{f(p.equity)}</b></span>
      <span>Deployed: <b>{f(p.deployed)}</b> ({f((p.deployed_frac || 0) * 100, 0)}%)
        <Hint text="Total value in open positions across all strategies, and as a % of equity. The portfolio cap blocks new entries past your max." />
      </span>
      <span>Open: <b>{p.open_positions ?? 0}</b>
        <Hint text="How many strategies hold a position right now, across the whole portfolio." />
      </span>
      <span>Day P&L: <b className={pnl >= 0 ? 'pos' : 'neg'}>{pnl >= 0 ? '+' : ''}{f(pnl)}</b>
        <Hint text="Aggregate realized P&L across all strategies today. Past the portfolio daily-loss limit, the portfolio kill switch trips." />
      </span>
      {halted && <span className="neg">⛔ PORTFOLIO KILL SWITCH: {p.kill_switch.reason}</span>}
    </div>
  )
}
