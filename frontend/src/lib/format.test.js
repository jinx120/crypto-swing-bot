import { describe, it, expect } from 'vitest'
import { formatMoney, formatSignedPct, formatSignedMoney } from './format.js'

describe('format', () => {
  it('formats money with two decimals and separators', () => {
    expect(formatMoney(10842.334)).toBe('$10,842.33')
  })
  it('formats signed percent from a fraction', () => {
    expect(formatSignedPct(0.032)).toBe('+3.2%')
    expect(formatSignedPct(-0.004)).toBe('-0.4%')
  })
  it('formats signed money', () => {
    expect(formatSignedMoney(342)).toBe('+$342.00')
    expect(formatSignedMoney(-12)).toBe('-$12.00')
  })
})
