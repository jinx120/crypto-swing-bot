import { useEffect, useRef } from 'react'
import { createChart, AreaSeries } from 'lightweight-charts'
import { api } from '../api.js'

const UP = '#2bd97a'

// A compact, non-interactive price sparkline for a coin card. Clicks pass through
// to the card (pointer-events: none) so the card still navigates to the detail page.
export default function MiniChart({ symbol, timeframe = '15m', bars = 60, height = 56 }) {
  const elRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)

  useEffect(() => {
    if (!elRef.current || chartRef.current) return
    const chart = createChart(elRef.current, {
      height,
      layout: { background: { color: 'transparent' }, textColor: 'transparent' },
      grid: { vertLines: { visible: false }, horzLines: { visible: false } },
      rightPriceScale: { visible: false },
      leftPriceScale: { visible: false },
      timeScale: { visible: false, borderVisible: false },
      crosshair: { mode: 0 },
      handleScroll: false,
      handleScale: false,
    })
    const series = chart.addSeries(AreaSeries, {
      lineColor: UP,
      topColor: 'rgba(43, 217, 122, 0.25)',
      bottomColor: 'rgba(43, 217, 122, 0)',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    })
    chartRef.current = chart
    seriesRef.current = series
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null }
  }, [height])

  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const resp = await api.candles(symbol, timeframe, bars)
        if (!alive || !seriesRef.current) return
        const data = (resp?.candles || []).map((c) => ({ time: c.time, value: c.close }))
        seriesRef.current.setData(data)
        chartRef.current?.timeScale().fitContent()
      } catch { /* a data hiccup shouldn't break the card */ }
    }
    load()
    const id = setInterval(load, 30000)
    return () => { alive = false; clearInterval(id) }
  }, [symbol, timeframe, bars])

  return <div ref={elRef} style={{ width: '100%', height, pointerEvents: 'none' }} />
}
