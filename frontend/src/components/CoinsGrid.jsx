import { Plus } from 'lucide-react'
import CoinCard from './CoinCard.jsx'
import { Button } from './ui/button.jsx'

export default function CoinsGrid({ state, health, prices, onChange, onAdd }) {
  const strategies = state?.strategies || []
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Coins</h2>
        <Button size="sm" variant="outline" onClick={onAdd}>
          <Plus className="h-3.5 w-3.5" /> Add coin
        </Button>
      </div>
      {strategies.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          No coins armed yet. Use “Add coin” to start trading a symbol.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {strategies.map((s) => (
            <CoinCard key={s.name} strategy={s} health={health} price={prices?.[s.symbol]} onChange={onChange} />
          ))}
        </div>
      )}
    </section>
  )
}
