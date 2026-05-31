import { useEffect, useRef, useState } from 'react'
import {
  createChart, CandlestickSeries, HistogramSeries, LineSeries, createSeriesMarkers,
} from 'lightweight-charts'
import { api } from '../api.js'
import Hint from './Hint.jsx'

const UP = '#36d17a'
const DOWN = '#ff5470'
const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d']

// Declarative toggle registry — add a row here to expose a new overlay/option.
const TOGGLES = [
  ['volume', 'Volume'],
  ['markers', 'Trade markers'],
  ['entryLine', 'Entry line'],
  ['stopLine', 'Stop line'],
  ['tpLine', 'Target line'],
  ['sma', 'SMA'],
  ['ema', 'EMA'],
  ['grid', 'Grid'],
  ['magnet', 'Magnet crosshair'],
  ['logScale', 'Log scale'],
]

const DEFAULT_CFG = {
  timeframe: null,              // null = follow the active strategy profile
  volume: true, markers: true,
  entryLine: true, stopLine: true, tpLine: true,
  grid: true, magnet: true, logScale: false,
  sma: false, smaPeriod: 20,
  ema: false, emaPeriod: 50,
}
const CFG_KEY = 'swingbot_chart_cfg'

function loadCfg() {
  try { return { ...DEFAULT_CFG, ...JSON.parse(localStorage.getItem(CFG_KEY) || '{}') } }
  catch { return { ...DEFAULT_CFG } }
}

// ── indicators (computed client-side from close prices) ──
function sma(candles, period) {
  const out = []; let sum = 0
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i].close
    if (i >= period) sum -= candles[i - period].close
    if (i >= period - 1) out.push({ time: candles[i].time, value: sum / period })
  }
  return out
}
function ema(candles, period) {
  const out = []; const k = 2 / (period + 1); let prev
  for (let i = 0; i < candles.length; i++) {
    const c = candles[i].close
    prev = i === 0 ? c : c * k + prev * (1 - k)
    if (i >= period - 1) out.push({ time: candles[i].time, value: prev })
  }
  return out
}

// entry/exit markers from the journal, sorted by time
function tradeMarkers(trades) {
  if (!trades?.length) return []
  const m = []
  for (const t of trades) {
    const entry = Math.floor(Date.parse(t.entry_ts) / 1000)
    const exit = Math.floor(Date.parse(t.exit_ts) / 1000)
    if (Number.isFinite(entry)) m.push({ time: entry, position: 'belowBar', color: UP, shape: 'arrowUp', text: 'BUY' })
    if (Number.isFinite(exit)) m.push({ time: exit, position: 'aboveBar', color: t.pnl >= 0 ? UP : DOWN, shape: 'arrowDown', text: t.pnl >= 0 ? 'SELL +' : 'SELL −' })
  }
  return m.sort((a, b) => a.time - b.time)
}

export default function ChartPanel({ symbol, trades, position }) {
  const boxRef = useRef(null)
  const chartRef = useRef(null)
  const candleRef = useRef(null)
  const volRef = useRef(null)
  const smaRef = useRef(null)
  const emaRef = useRef(null)
  const markersRef = useRef(null)
  const linesRef = useRef([])         // active price-line handles
  const dataRef = useRef([])          // last candle array (for indicator recompute)
  const fittedRef = useRef(false)

  const [cfg, setCfg] = useState(loadCfg)
  const [showCfg, setShowCfg] = useState(false)
  const [meta, setMeta] = useState({ symbol, timeframe: '' })
  const [count, setCount] = useState(null)
  const [err, setErr] = useState('')

  const activeTf = cfg.timeframe || meta.timeframe || ''
  const set = (patch) => setCfg(c => ({ ...c, ...patch }))

  useEffect(() => { localStorage.setItem(CFG_KEY, JSON.stringify(cfg)) }, [cfg])

  // ── create chart + all series once ──
  useEffect(() => {
    const chart = createChart(boxRef.current, {
      autoSize: true,
      layout: { background: { color: 'transparent' }, textColor: 'rgba(237,237,239,0.65)',
        fontFamily: 'Inter, ui-sans-serif, system-ui, sans-serif', attributionLogo: false },
      grid: { vertLines: { color: 'rgba(255,255,255,0.04)' }, horzLines: { color: 'rgba(255,255,255,0.04)' } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
      timeScale: { borderColor: 'rgba(255,255,255,0.08)', timeVisible: true, secondsVisible: false },
    })
    chartRef.current = chart
    candleRef.current = chart.addSeries(CandlestickSeries, {
      upColor: UP, downColor: DOWN, wickUpColor: UP, wickDownColor: DOWN, borderVisible: false })
    volRef.current = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: '' })
    volRef.current.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    smaRef.current = chart.addSeries(LineSeries, { color: '#f5a623', lineWidth: 2, priceLineVisible: false, lastValueVisible: false })
    emaRef.current = chart.addSeries(LineSeries, { color: '#6c7bf2', lineWidth: 2, priceLineVisible: false, lastValueVisible: false })
    markersRef.current = createSeriesMarkers(candleRef.current, [])
    return () => chart.remove()
  }, [])

  // ── fetch candles for the active timeframe, poll every 10s ──
  useEffect(() => {
    let alive = true
    const load = async () => {
      try {
        const sym = meta.symbol || symbol
        const r = (cfg.timeframe && sym)
          ? await api.candles(sym, cfg.timeframe)
          : await api.candles()
        if (!alive) return
        setErr('')
        setMeta({ symbol: r.symbol, timeframe: r.timeframe })
        const candles = r.candles || []
        dataRef.current = candles
        setCount(candles.length)
        candleRef.current?.setData(candles.map(c => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })))
        volRef.current?.setData(candles.map(c => ({ time: c.time, value: c.volume,
          color: c.close >= c.open ? 'rgba(54,209,122,0.4)' : 'rgba(255,84,112,0.4)' })))
        applyIndicators()
        if (candles.length && !fittedRef.current) { chartRef.current?.timeScale().fitContent(); fittedRef.current = true }
      } catch (e) { if (alive) setErr(e.message) }
    }
    load()
    const id = setInterval(load, 10000)
    return () => { alive = false; clearInterval(id) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfg.timeframe, symbol])

  // recompute + show/hide indicator lines
  function applyIndicators() {
    const d = dataRef.current
    smaRef.current?.applyOptions({ visible: cfg.sma })
    emaRef.current?.applyOptions({ visible: cfg.ema })
    smaRef.current?.setData(cfg.sma ? sma(d, Math.max(1, cfg.smaPeriod)) : [])
    emaRef.current?.setData(cfg.ema ? ema(d, Math.max(1, cfg.emaPeriod)) : [])
  }

  // redraw position price lines (entry / stop / target)
  function applyLines() {
    const s = candleRef.current
    if (!s) return
    linesRef.current.forEach(l => s.removePriceLine(l)); linesRef.current = []
    const add = (price, color, title, style) => {
      if (price == null || !Number.isFinite(price)) return
      linesRef.current.push(s.createPriceLine({ price, color, lineWidth: 1, lineStyle: style,
        axisLabelVisible: true, title }))
    }
    if (cfg.entryLine) add(position?.entry_price, '#9aa7bd', 'entry', 0)
    if (cfg.stopLine) add(position?.stop, DOWN, 'stop', 2)
    if (cfg.tpLine) add(position?.tp, UP, 'target', 2)
  }

  // ── apply visual config whenever cfg or position changes ──
  useEffect(() => {
    const chart = chartRef.current; if (!chart) return
    chart.applyOptions({
      grid: { vertLines: { visible: cfg.grid }, horzLines: { visible: cfg.grid } },
      crosshair: { mode: cfg.magnet ? 1 : 0 },
    })
    candleRef.current?.priceScale().applyOptions({ mode: cfg.logScale ? 2 : 0 })
    volRef.current?.applyOptions({ visible: cfg.volume })
    markersRef.current?.setMarkers(cfg.markers ? tradeMarkers(trades) : [])
    applyIndicators()
    applyLines()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfg, trades, position])

  const label = meta.symbol || symbol || '—'
  return (
    <div className="panel full chart-panel">
      <h3>Price
        <Hint text="Live OHLC candles for the selected timeframe, pulled from Alpaca into the local market-data store. ▲/▼ mark the bot's entries/exits; dashed lines show the open position's stop & target. Toggle overlays with the gear." />
        <span className="chart-sym">{label}</span>
        <div className="chart-tfs">
          {TIMEFRAMES.map(tf => (
            <button key={tf} className={`tf ${activeTf === tf ? 'active' : ''}`}
              onClick={() => set({ timeframe: tf })}>{tf}</button>
          ))}
          <button className={`tf gear ${showCfg ? 'active' : ''}`} title="Chart settings"
            onClick={() => setShowCfg(s => !s)} aria-label="Chart settings">⚙</button>
        </div>
      </h3>

      {showCfg && (
        <div className="chart-cfg">
          {TOGGLES.map(([key, lbl]) => (
            <label key={key} className="cfg-row">
              <input type="checkbox" checked={!!cfg[key]} onChange={e => set({ [key]: e.target.checked })} />
              <span>{lbl}</span>
              {key === 'sma' && <input type="number" className="cfg-num" min="1" max="400"
                value={cfg.smaPeriod} onChange={e => set({ smaPeriod: +e.target.value })} />}
              {key === 'ema' && <input type="number" className="cfg-num" min="1" max="400"
                value={cfg.emaPeriod} onChange={e => set({ emaPeriod: +e.target.value })} />}
            </label>
          ))}
        </div>
      )}

      <div className="chart-box" ref={boxRef} />
      {err && <div className="err">{err}</div>}
      {count === 0 && !err && (
        <div className="chart-empty">Waiting for market data — set Alpaca credentials and an active strategy, then the poller fills this in within a minute.</div>
      )}
      {count === null && !err && <div className="chart-empty">Loading chart…</div>}
    </div>
  )
}
