export default function PositionPanel({ position }){
  if (!position) return <div className="panel"><h3>Position</h3><div>Flat — waiting for signal</div></div>
  return (
    <div className="panel">
      <h3>Position</h3>
      <div className="row"><span>Entry</span><span>{position.entry_price}</span></div>
      <div className="row"><span>Qty</span><span>{position.qty}</span></div>
      <div className="row"><span>Stop</span><span className="neg">{position.stop?.toFixed?.(6)}</span></div>
      <div className="row"><span>Take-profit</span><span className="pos">{position.tp?.toFixed?.(6)}</span></div>
      <div className="row"><span>Max hold until</span><span>{position.max_hold_until}</span></div>
    </div>
  )
}
