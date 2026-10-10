import { describe, expect, it } from 'vitest'

import type { PaymentMethod } from '../../lib/api/types'
import { cashRounding, payPlan, quickCash } from './payDraft'

const methods: PaymentMethod[] = [
  { code: 'cash', name: 'Cash', kind: 'cash', active: true },
  { code: 'qris', name: 'QRIS', kind: 'qris_static', active: true },
]

describe('pay plan (FR-SAL-006)', () => {
  it('rounds cash half up like the server', () => {
    expect(cashRounding(27_550, 100)).toBe(50)
    expect(cashRounding(27_549, 100)).toBe(-49)
    expect(cashRounding(27_549, 0)).toBe(0)
  })

  it('pays a single cash tender in full and gives change', () => {
    const plan = payPlan({
      total: 66_000,
      tip: 0,
      rows: [{ method: 'cash', amount: '', tendered: '100.000' }],
      methods,
      roundingStep: 0,
      currency: 'IDR',
    })
    expect(plan.change).toBe(34_000)
    expect(plan.body?.payments).toEqual([{ method: 'cash', amount: 66_000, tendered: 100_000 }])
  })

  it('splits tenders and blocks until they add up', () => {
    const rows = [
      { method: 'cash', amount: '50.000', tendered: '' },
      { method: 'qris', amount: '10.000', tendered: '' },
    ]
    const short = payPlan({
      total: 66_000,
      tip: 0,
      rows,
      methods,
      roundingStep: 100,
      currency: 'IDR',
    })
    expect(short.body).toBeNull()
    expect(short.rounding).toBe(0) // not all cash: no rounding
    rows[1].amount = '16.000'
    const ok = payPlan({ total: 66_000, tip: 0, rows, methods, roundingStep: 100, currency: 'IDR' })
    expect(ok.body?.payments.map((p) => p.amount)).toEqual([50_000, 16_000])
  })

  it('needs a code for a voucher tender and sends it (FR-SAL-016)', () => {
    const withVoucher: PaymentMethod[] = [
      ...methods,
      { code: 'v', name: 'Voucher', kind: 'voucher', active: true },
    ]
    const input = { total: 20_000, tip: 0, methods: withVoucher, roundingStep: 0, currency: 'IDR' }
    const row = { method: 'v', amount: '', tendered: '' }
    expect(payPlan({ ...input, rows: [row] }).body).toBeNull()
    const ok = payPlan({ ...input, rows: [{ ...row, reference: ' ab12-cd34 ' }] })
    expect(ok.body?.payments).toEqual([
      { method: 'v', amount: 20_000, tendered: null, reference: 'ab12-cd34' },
    ])
  })

  it('offers exact cash and the next round notes', () => {
    expect(quickCash(66_000)).toEqual([66_000, 70_000, 80_000, 100_000])
  })
})
