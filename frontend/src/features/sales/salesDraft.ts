import type { DayEntryIn } from '../../lib/api/types'

const QTY = /^\d{1,14}([.,]\d{1,4})?$/
const MONEY = /^\d{1,15}$/
const num = (v: string) => Number(v.replace(',', '.'))

export type Quantities = Record<string, string>

export const filledLines = (qty: Quantities) => Object.entries(qty).filter(([, v]) => v !== '')

export function entryOk(qty: Quantities, reported: string): boolean {
  const filled = filledLines(qty)
  const linesOk = filled.every(([, v]) => QTY.test(v) && num(v) > 0)
  return filled.length > 0 && linesOk && (reported === '' || MONEY.test(reported))
}

export function listTotal(rows: { item_id: string; price: number }[], qty: Quantities): number {
  return Math.round(rows.reduce((sum, r) => sum + num(qty[r.item_id] || '0') * r.price, 0))
}

export function toEntry(
  where: { outletId: string; on: string; channelId: string },
  qty: Quantities,
  reported: string,
): DayEntryIn {
  return {
    outlet_id: where.outletId,
    business_date: where.on,
    channel_id: where.channelId,
    lines: filledLines(qty).map(([item_id, v]) => ({ item_id, qty: v.replace(',', '.') })),
    reported_total: reported === '' ? null : Number(reported),
  }
}
