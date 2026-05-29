export default function JournalTable({ trades }){
  return (
    <div className="panel full">
      <h3>Journal</h3>
      <table><thead><tr>
        <th>Exit</th><th>Entry $</th><th>Exit $</th><th>P&L</th><th>Reason</th><th>Score</th><th>Regime</th>
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
