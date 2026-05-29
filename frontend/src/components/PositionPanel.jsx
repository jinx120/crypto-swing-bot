import Hint from './Hint.jsx'

export default function PositionPanel({ position }){
  if (!position) return (
    <div className="panel"><h3>Position
      <Hint text="Your current holding in this coin. “Flat” means none — the bot is waiting for an entry signal." />
    </h3><div>Flat — waiting for signal</div></div>
  )
  return (
    <div className="panel">
      <h3>Position</h3>
      <div className="row"><span>Entry
        <Hint text="The price the bot bought at. Profit/loss is measured from here." /></span><span>{position.entry_price}</span></div>
      <div className="row"><span>Qty
        <Hint text="How much of the coin is held. Size is set so that hitting the stop loses only your configured risk-per-trade." /></span><span>{position.qty}</span></div>
      <div className="row"><span>Stop
        <Hint text="Stop-loss: if price falls to here the bot auto-sells to cap the loss. Placed at entry − (stop multiple × ATR), so it adapts to how volatile the coin is." /></span><span className="neg">{position.stop?.toFixed?.(6)}</span></div>
      <div className="row"><span>Take-profit
        <Hint text="Target price: if price rises to here the bot auto-sells to lock in the gain. Placed at entry + (take-profit multiple × ATR)." /></span><span className="pos">{position.tp?.toFixed?.(6)}</span></div>
      <div className="row"><span>Max hold until
        <Hint text="Time-based exit. If neither the stop nor target is hit by this time, the bot closes the trade anyway so capital isn’t tied up indefinitely." /></span><span>{position.max_hold_until}</span></div>
    </div>
  )
}
