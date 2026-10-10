import { describe, expect, it } from 'vitest'

import type { MenuItemOut, OfflinePackOut } from '../../../lib/api/types'
import { addToCart, changeQty, checkout, linePrice } from './cart'

const item = {
  id: 'i1',
  name: 'Nasi',
  price: 25_000,
  modifier_groups: [{ id: 'g', options: [{ id: 'egg', price_delta: 5_000 }] }],
} as unknown as MenuItemOut
const pack = {
  channel_code: 'dine_in',
  tax: { rules: [{ id: 't', rate_bp: 1000, price_includes_tax: false }] },
  service_charge: { enabled: false },
  cash_rounding_step: 100,
  methods: [{ code: 'cash', kind: 'cash', active: true, name: 'Cash' }],
} as unknown as OfflinePackOut

describe('FR-SAL-013 offline cart', () => {
  it('merges the same choice and prices options', () => {
    let lines = addToCart([], { item, optionIds: ['egg'], note: '' })
    lines = addToCart(lines, { item, optionIds: ['egg'], note: '' })
    expect(lines).toHaveLength(1)
    expect(linePrice(lines[0])).toBe(60_000)
    expect(changeQty(lines, lines[0].key, -2)).toHaveLength(0)
  })

  it('needs enough cash before the order can finish', () => {
    const lines = addToCart([], { item, optionIds: [], note: '' })
    const base = { lines, pack, outletId: 'o', method: 'cash', currency: 'IDR' }
    expect(checkout({ ...base, tendered: '20000' }).ready).toBe(false)
    const paid = checkout({ ...base, tendered: '30000' })
    expect(paid.totals.total).toBe(27_500)
    expect(paid.plan?.change).toBe(2_500)
    expect(checkout({ ...base, method: null, tendered: '' }).ready).toBe(true)
  })
})
