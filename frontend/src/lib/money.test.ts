import { describe, expect, it } from 'vitest'

import { parseMoney } from './money'

describe('parseMoney (minor units, never floats)', () => {
  it('reads IDR with any grouping', () => {
    for (const text of ['25000', '25.000', '25,000', ' 25 000 ']) {
      expect(parseMoney(text, 'IDR')).toBe(25000)
    }
    expect(parseMoney('0', 'IDR')).toBe(0)
  })

  it('reads two-digit currencies with one decimal mark', () => {
    expect(parseMoney('12.5', 'USD')).toBe(1250)
    expect(parseMoney('12,05', 'USD')).toBe(1205)
    expect(parseMoney('12', 'USD')).toBe(1200)
  })

  it('refuses invalid or out-of-range amounts', () => {
    for (const text of ['', '-1', 'abc', '1e5', '12.345']) {
      expect(parseMoney(text, 'USD')).toBeNull()
    }
    expect(parseMoney('-5', 'IDR')).toBeNull()
    expect(parseMoney('9999999999999', 'IDR')).toBeNull()
  })
})
