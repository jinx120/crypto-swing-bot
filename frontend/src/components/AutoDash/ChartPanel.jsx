import { useEffect, useRef } from 'react'
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts'
import { api } from '../../api.js'
import usePolling from './usePolling.js'

const UP = '#36d17a'
const DOWN = '#ff5470'

export default function ChartPanel() {
  const { data: candles } = usePolling(api.auto.candles, 10000)
  const { data: trades } = usePolling(api.auto.trades, 10000)
  const elRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)

  useEffect(() => {
    if (!elRef.current || chartRef.current) return
    const chart = createChart(elRef.current, {
      height: 320, layout: { background: { color: 'transparent' }, textColor: '#ccc' },
      grid: { vertLines: { color: '#222' }, horzLines: { color: '#222' } },
      timeScale: { timeVisible: true },
    })
    const series = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, borderVisible: false,
      wickUpColor: UP, wickDownColor: DOWN,
    })
    chartRef.current = chart
    seriesRef.current = series
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null }
  }, [])

  useEffect(() => {
    if (!seriesRef.current || !candles) return
    seriesRef.current.setData(candles.map(c => ({
      time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })))
    const markers = (trades || [])
      .filter(t => t.ts)
      .map(t => ({
        time: Math.floor(new Date(t.ts).getTime() / 1000),
        position: 'aboveBar', color: t.won ? UP : DOWN, shape: 'circle',
        text: (t.pnl >= 0 ? '+' : '') + Number(t.pnl).toFixed(0),
      }))
      .sort((a, b) => a.time - b.time)
    createSeriesMarkers(seriesRef.current, markers)
    chartRef.current?.timeScale().fitContent()
  }, [candles, trades])

  return (
    <div className="panel full">
      <h3>BTC/USD candles</h3>
      <div ref={elRef} style={{ width: '100%' }} />
    </div>
  )
}
