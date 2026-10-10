import { describe, expect, it } from 'vitest'

import { offlineTotals, roundHalfUpDiv } from './totals'

const rule = (over: Record<string, unknown> = {}) => ({
  id: 'pbjt',
  name: 'PBJT',
  rate_bp: 1000,
  applies_to_service_charge: true,
  price_includes_tax: false,
  order: 0,
  outlet_ids: null,
  active: true,
  ...over,
})
const pack = (rules: ReturnType<typeof rule>[], sc = { enabled: false, rate_bp: 0 }) => ({
  tax: { rules },
  service_charge: { channels: [], before_tax: true, ...sc },
  channel_code: 'dine_in',
})

describe('offline totals (same as backend pricing.py)', () => {
  it('rounds half away from zero', () => {
    expect(roundHalfUpDiv(5, 2)).toBe(3)
    expect(roundHalfUpDiv(-5, 2)).toBe(-3)
  })
  it('adds exclusive tax on net plus service charge', () => {
    const t = offlineTotals([50_000], pack([rule()], { enabled: true, rate_bp: 500 }), 'o1')
    expect(t).toEqual({ subtotal: 50_000, serviceCharge: 2_500, tax: 5_250, total: 57_750 })
  })
  it('splits inclusive tax so the total is the price paid', () => {
    const t = offlineTotals([33_333], pack([rule({ price_includes_tax: true })]), 'o1')
    expect(t.total).toBe(33_333)
    expect(t.tax).toBe(3_030)
  })
  it('skips rules for other outlets and inactive ones', () => {
    const rules = [rule({ outlet_ids: ['o2'] }), rule({ id: 'x', active: false })]
    expect(offlineTotals([10_000], pack(rules), 'o1').total).toBe(10_000)
  })
})
