import { useEffect, useRef, useState } from 'react'

// Polls `fetcher()` immediately and every `intervalMs`. Keeps the last good
// value on transient errors (never blanks the panel).
export default function usePolling(fetcher, intervalMs = 10000) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fetcher)
  fnRef.current = fetcher

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const d = await fnRef.current()
        if (alive) { setData(d); setError(''); setLoading(false) }
      } catch (e) {
        if (alive) { setError(e.message || 'error'); setLoading(false) }
      }
    }
    tick()
    const id = setInterval(tick, intervalMs)
    return () => { alive = false; clearInterval(id) }
  }, [intervalMs])

  return { data, error, loading }
}
