import { describe, expect, it } from 'vitest'

import { bpToPercent, percentToBp, optionalPercentOk } from './percent'

describe('percent and basis points', () => {
  it('parses whole and decimal percentages with dot or comma', () => {
    expect(percentToBp('10')).toBe(1000)
    expect(percentToBp('10.5')).toBe(1050)
    expect(percentToBp('10,25')).toBe(1025)
    expect(percentToBp('0')).toBe(0)
    expect(percentToBp('100')).toBe(10000)
  })
  it('rejects invalid input instead of guessing', () => {
    for (const bad of ['', 'abc', '101', '10.123', '-5', '1e2']) expect(percentToBp(bad)).toBeNull()
  })
  it('formats for the locale and round-trips', () => {
    expect(bpToPercent(1050, 'id')).toBe('10,5')
    expect(bpToPercent(1025, 'en')).toBe('10.25')
    expect(bpToPercent(1000, 'en')).toBe('10')
    for (const bp of [0, 1, 99, 1000, 1234, 10000])
      expect(percentToBp(bpToPercent(bp, 'en'))).toBe(bp)
  })
})

describe('optionalPercentOk', () => {
  it('allows empty, rejects 0 and above 100', () => {
    expect(optionalPercentOk('')).toBe(true)
    expect(optionalPercentOk('35,5')).toBe(true)
    expect(optionalPercentOk('0')).toBe(false)
    expect(optionalPercentOk('101')).toBe(false)
  })
})
