import { api } from '../../api.js'
import usePolling from './usePolling.js'

export default function CurrentPositionPanel() {
  const { data: pos } = usePolling(api.auto.position, 3000)
  return (
    <div className="panel">
      <h3>Current position</h3>
      {!pos ? <div>No open position (flat).</div> : (
        <div>
          <div>Symbol: <b>{pos.symbol}</b></div>
          <div>Entry: <b>{Number(pos.entry_price).toFixed(2)}</b></div>
          <div>Qty: <b>{Number(pos.qty)}</b></div>
          <div>Stop: <b>{pos.stop != null ? Number(pos.stop).toFixed(2) : '—'}</b></div>
          <div>Target: <b>{pos.tp != null ? Number(pos.tp).toFixed(2) : '—'}</b></div>
        </div>
      )}
    </div>
  )
}
