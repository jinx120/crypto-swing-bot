import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Polls /api/price every `intervalMs` for the given symbols. Returns a map
// { symbol: { price, ts, stale } }. Candle/chart cadence is unaffected.
export default function useLivePrice(symbols, intervalMs = 3000) {
  const [prices, setPrices] = useState({})
  const key = (symbols || []).slice().sort().join(',')
  const ref = useRef(symbols)
  ref.current = symbols

  useEffect(() => {
    if (!key) return
    let alive = true
    const tick = async () => {
      try { const d = await api.price(ref.current); if (alive) setPrices(d) } catch { /* keep last */ }
    }
    tick()
    const id = setInterval(tick, intervalMs)
    return () => { alive = false; clearInterval(id) }
  }, [key, intervalMs])

  return prices
}
