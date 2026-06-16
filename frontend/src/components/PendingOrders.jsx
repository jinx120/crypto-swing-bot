import Hint from './Hint.jsx'

const fmtTs = (iso) => iso ? new Date(iso).toLocaleString() : '-'

export default function PendingOrders({ orders = [] }) {
  if (!orders.length) return null
  return (
    <div className="panel full">
      <h3>Pending orders <span className="chip">{orders.length}</span>
        <Hint text="Orders that have been sent to the broker but not yet confirmed filled. They survive restarts and are reconciled against the broker before any position is created." />
      </h3>
      <table>
        <thead><tr><th>Strategy</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Submitted</th><th>Client order id</th></tr></thead>
        <tbody>
          {orders.map(o => (
            <tr key={o.client_order_id}>
              <td>{o.strategy}</td><td>{o.symbol}</td><td>{o.side}</td>
              <td>{o.requested_qty}</td><td>{fmtTs(o.submitted_at)}</td><td>{o.client_order_id}</td>
            </tr>))}
        </tbody>
      </table>
    </div>
  )
}
