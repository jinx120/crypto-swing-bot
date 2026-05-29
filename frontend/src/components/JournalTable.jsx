import Hint from './Hint.jsx'

export default function JournalTable({ trades }){
  return (
    <div className="panel full">
      <h3>Journal
        <Hint text="A log of every closed trade, newest first — what the bot actually did. Use it to sanity-check that entries and exits match what you intended." />
      </h3>
      <table><thead><tr>
        <th>Exit</th><th>Entry $</th><th>Exit $</th><th>P&L</th>
        <th>Reason<Hint text="Why the trade closed: stop = stop-loss hit, take_profit = target hit, time/max_hold = held too long, flatten = you closed it manually." /></th>
        <th>Score<Hint text="The confluence score at the moment the bot entered — how strong the buy case was." /></th>
        <th>Regime<Hint text="The trend regime at entry. Helps you see whether winners and losers cluster in particular market conditions." /></th>
      </tr></thead><tbody>
        {(trades||[]).slice(-25).reverse().map((t,i)=>(
          <tr key={i}>
            <td>{(t.exit_ts||'').slice(0,16)}</td><td>{t.entry_price?.toFixed?.(6)}</td>
            <td>{t.exit_price?.toFixed?.(6)}</td>
            <td className={t.pnl>=0?'pos':'neg'}>{t.pnl>=0?'+':''}{t.pnl?.toFixed?.(2)}</td>
            <td>{t.exit_reason}</td><td>{t.score_at_entry?.toFixed?.(2)}</td><td>{t.regime_at_entry}</td>
          </tr>
        ))}
        {(!trades || trades.length===0) && <tr><td colSpan="7">No trades yet</td></tr>}
      </tbody></table>
    </div>
  )
}
