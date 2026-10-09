import { describe, expect, it } from 'vitest'

import { entryOk, listTotal, toEntry } from './salesDraft'

describe('daily sales entry', () => {
  it('needs at least one valid quantity and a whole-number reported total', () => {
    expect(entryOk({}, '')).toBe(false)
    expect(entryOk({ a: '2' }, '')).toBe(true)
    expect(entryOk({ a: '2,5' }, '45000')).toBe(true)
    expect(entryOk({ a: '0' }, '')).toBe(false)
    expect(entryOk({ a: '2' }, '4.5')).toBe(false)
  })

  it('totals at list price and builds the body with exact decimals', () => {
    expect(listTotal([{ item_id: 'a', price: 25000 }], { a: '3' })).toBe(75000)
    const body = toEntry(
      { outletId: 'o', on: '2026-03-05', channelId: 'c' },
      { a: '1,5', b: '' },
      '',
    )
    expect(body.lines).toEqual([{ item_id: 'a', qty: '1.5' }])
    expect(body.reported_total).toBeNull()
  })
})
