import { useEffect, useMemo, useRef } from 'react'
import { createChart, CandlestickSeries, createSeriesMarkers } from 'lightweight-charts'
import { api } from '../../api.js'
import usePolling from './usePolling.js'
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card.jsx'

const UP = '#2bd97a'
const DOWN = '#ff4d6d'

export default function ChartPanel({ symbol, strategy, timeframe = '15m' }) {
  const candlesFetcher = useMemo(() => () => api.candles(symbol, timeframe, 500), [symbol, timeframe])
  const tradesFetcher = useMemo(() => () => api.journal(strategy), [strategy])
  const { data: candleResp } = usePolling(candlesFetcher, 10000)
  const { data: trades } = usePolling(tradesFetcher, 10000)
  const elRef = useRef(null)
  const chartRef = useRef(null)
  const seriesRef = useRef(null)

  useEffect(() => {
    if (!elRef.current || chartRef.current) return
    const chart = createChart(elRef.current, {
      height: 360, layout: { background: { color: 'transparent' }, textColor: '#9aa4b2' },
      grid: { vertLines: { color: '#1c2530' }, horzLines: { color: '#1c2530' } },
      timeScale: { timeVisible: true },
    })
    const series = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, borderVisible: false, wickUpColor: UP, wickDownColor: DOWN,
    })
    chartRef.current = chart; seriesRef.current = series
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null }
  }, [])

  useEffect(() => {
    if (!seriesRef.current) return
    const candles = candleResp?.candles || []
    seriesRef.current.setData(candles.map((c) => ({
      time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    })))
    const markers = (trades || [])
      .filter((t) => t.exit_ts)
      .map((t) => ({
        time: Math.floor(new Date(t.exit_ts).getTime() / 1000),
        position: 'aboveBar', color: t.pnl >= 0 ? UP : DOWN, shape: 'circle',
        text: (t.pnl >= 0 ? '+' : '') + Number(t.pnl).toFixed(0),
      }))
      .sort((a, b) => a.time - b.time)
    createSeriesMarkers(seriesRef.current, markers)
    chartRef.current?.timeScale().fitContent()
  }, [candleResp, trades])

  return (
    <Card>
      <CardHeader><CardTitle>{symbol} candles</CardTitle></CardHeader>
      <CardContent><div ref={elRef} style={{ width: '100%' }} /></CardContent>
    </Card>
  )
}
