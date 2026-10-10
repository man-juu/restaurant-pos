import { describe, expect, it } from 'vitest'

import { formatDateTime, formatMoney, formatNumber } from './format'

describe('formatting (FR-X-002)', () => {
  it('formats IDR without minor units in both locales', () => {
    expect(formatMoney(25000, 'IDR', 'id-ID').replace(/\s/g, ' ')).toBe('Rp 25.000')
    expect(formatMoney(25000, 'IDR', 'en-GB')).toContain('25,000')
  })
  it('uses two minor digits for other currencies', () => {
    expect(formatMoney(1999, 'USD', 'en-GB')).toBe('US$19.99')
  })
  it('formats numbers and converts UTC to the outlet timezone', () => {
    expect(formatNumber(1234567, 'id-ID')).toBe('1.234.567')
    expect(formatDateTime('2026-10-07T17:30:00Z', 'en-GB', 'Asia/Jakarta')).toContain('00:30')
  })
})
