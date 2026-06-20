import { describe, it, expect } from 'vitest'
import {
  loopState, modeBadge, equityOf, dayPnl, dayPnlPct, reliabilityPct,
  brokerUnauthorized, cardStatus, availableToAdd, lastDecision,
} from './derive.js'

describe('loopState', () => {
  it('RUNNING when thread alive and not paused', () => {
    expect(loopState({ lifecycle: { running_actual: true, paused: false, halted: false } })).toBe('RUNNING')
  })
  it('PAUSED when paused or halted', () => {
    expect(loopState({ lifecycle: { running_actual: true, paused: true } })).toBe('PAUSED')
    expect(loopState({ lifecycle: { running_actual: true, halted: true } })).toBe('PAUSED')
  })
  it('STOPPED when no thread', () => {
    expect(loopState({ lifecycle: { running_actual: false } })).toBe('STOPPED')
    expect(loopState(null)).toBe('STOPPED')
  })
})

describe('modeBadge', () => {
  it('uppercases mode, defaults PAPER', () => {
    expect(modeBadge({ portfolio: { mode: 'live' } })).toBe('LIVE')
    expect(modeBadge({})).toBe('PAPER')
  })
})

describe('equity/pnl', () => {
  it('reads equity and day pnl', () => {
    const s = { portfolio: { equity: 10000, day_pnl: 210 } }
    expect(equityOf(s)).toBe(10000)
    expect(dayPnl(s)).toBe(210)
    expect(dayPnlPct(s)).toBeCloseTo(2.1, 5)
  })
  it('null-safe', () => {
    expect(equityOf({})).toBe(null)
    expect(dayPnlPct({ portfolio: { equity: 0, day_pnl: 5 } })).toBe(null)
  })
})

describe('reliabilityPct', () => {
  it('scales ratio to percent', () => {
    expect(reliabilityPct({ reliability: { cycle_completion_ratio: 0.98 } })).toBeCloseTo(98)
    expect(reliabilityPct({ reliability: { cycle_completion_ratio: null } })).toBe(null)
    expect(reliabilityPct({})).toBe(null)
  })
})

describe('brokerUnauthorized', () => {
  it('true on auth-flavored startup_error', () => {
    expect(brokerUnauthorized({ lifecycle: { startup_error: 'unauthorized' } })).toBe(true)
    expect(brokerUnauthorized({ lifecycle: { startup_error: 'missing credentials' } })).toBe(true)
  })
  it('false otherwise', () => {
    expect(brokerUnauthorized({ lifecycle: { startup_error: null } })).toBe(false)
    expect(brokerUnauthorized({ lifecycle: { startup_error: 'no armed strategies' } })).toBe(false)
    expect(brokerUnauthorized(null)).toBe(false)
  })
})

describe('cardStatus', () => {
  it('long/short/flat/armed', () => {
    expect(cardStatus({ running: true, position: { qty: 0.01 } })).toBe('long')
    expect(cardStatus({ running: true, position: { qty: -0.01 } })).toBe('short')
    expect(cardStatus({ running: true, position: null })).toBe('flat')
    expect(cardStatus({ running: false, position: null })).toBe('armed')
  })
})

describe('availableToAdd', () => {
  it('universe minus watchlist', () => {
    expect(availableToAdd({ symbols: ['BTC/USD', 'ETH/USD', 'SOL/USD'] }, { symbols: ['BTC/USD'] }))
      .toEqual(['ETH/USD', 'SOL/USD'])
    expect(availableToAdd(null, null)).toEqual([])
  })
})

describe('lastDecision', () => {
  it('maps code+reason', () => {
    const h = { last_decisions_by_strategy: { btc_trend: { decision_code: 'ENTER', decision_reason: 'xover' } } }
    expect(lastDecision(h, 'btc_trend')).toEqual({ code: 'ENTER', reason: 'xover' })
    expect(lastDecision(h, 'eth_trend')).toBe(null)
    expect(lastDecision(null, 'x')).toBe(null)
  })
})
