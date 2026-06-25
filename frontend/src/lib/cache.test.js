import { describe, it, expect, beforeEach } from 'vitest'
import { readCache, writeCache } from './cache.js'

describe('localStorage cache', () => {
  beforeEach(() => {
    const store = new Map()
    globalThis.localStorage = {
      getItem: (k) => (store.has(k) ? store.get(k) : null),
      setItem: (k, v) => store.set(k, String(v)),
      removeItem: (k) => store.delete(k),
    }
  })

  it('round-trips JSON', () => {
    writeCache('k', { a: 1 })
    expect(readCache('k')).toEqual({ a: 1 })
  })

  it('returns null for a missing key', () => {
    expect(readCache('missing')).toBeNull()
  })

  it('never throws when storage is unavailable', () => {
    globalThis.localStorage = undefined
    expect(() => writeCache('k', { a: 1 })).not.toThrow()
    expect(readCache('k')).toBeNull()
  })
})
