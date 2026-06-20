import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

function Row({ k, v }) {
  return <div className="flex justify-between"><span className="text-muted-foreground">{k}</span><span className="font-mono tabular-nums">{v}</span></div>
}

export default function CurrentPositionPanel({ strategy: strat }) {
  const pos = strat?.position
  return (
    <Card>
      <CardHeader><CardTitle>Current position</CardTitle></CardHeader>
      <CardContent className="space-y-1 text-sm">
        {!pos ? <div className="text-muted-foreground">No open position (flat).</div> : (
          <>
            <Row k="Symbol" v={pos.symbol} />
            <Row k="Entry" v={Number(pos.entry_price).toFixed(2)} />
            <Row k="Qty" v={Number(pos.qty)} />
            <Row k="Mark" v={pos.mark_price != null ? Number(pos.mark_price).toFixed(2) : '—'} />
            <Row k="Unrealized" v={pos.unrealized != null ? Number(pos.unrealized).toFixed(2) : '—'} />
            <Row k="Stop" v={pos.stop != null ? Number(pos.stop).toFixed(2) : '—'} />
            <Row k="Target" v={pos.tp != null ? Number(pos.tp).toFixed(2) : '—'} />
          </>
        )}
      </CardContent>
    </Card>
  )
}
