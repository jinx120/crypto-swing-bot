import { describe, it, expect } from 'vitest'
import {
  loopState, modeBadge, equityOf, dayPnl, dayPnlPct, reliabilityPct,
  brokerUnauthorized, cardStatus, availableToAdd, lastDecision, buildProfilePatch,
  livePriceFor,
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

describe('buildProfilePatch', () => {
  it('returns only whitelisted changed keys', () => {
    const cur = { symbol: 'BTC/USD', entry_threshold: 0.05, poll_seconds: 60 }
    const patch = buildProfilePatch(cur, { entry_threshold: 0.2, poll_seconds: 5, symbol: 'X' })
    expect(patch).toEqual({ entry_threshold: 0.2 })
  })

  it('encodes regime toggle as allowed_regimes', () => {
    const patch = buildProfilePatch({ allowed_regimes: ['uptrend', 'neutral'] },
      { allowed_regimes: ['uptrend', 'neutral', 'downtrend'] })
    expect(patch.allowed_regimes).toEqual(['uptrend', 'neutral', 'downtrend'])
  })
})

describe('livePriceFor', () => {
  it('returns the quote for a symbol or null', () => {
    const prices = { 'BTC/USD': { price: 60810.2, stale: false } }
    expect(livePriceFor(prices, 'BTC/USD')).toEqual({ price: 60810.2, stale: false })
    expect(livePriceFor(prices, 'ETH/USD')).toBeNull()
    expect(livePriceFor(null, 'BTC/USD')).toBeNull()
  })
})
