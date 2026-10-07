import type { ItemSummary } from '../../lib/api/types'

export interface QtyLineDraft {
  item_id: string
  label: string
  qty: string
  unit_id: string
}

const QTY = /^\d{1,14}([.,]\d{1,4})?$/
const SIGNED = /^-?\d{1,14}([.,]\d{1,4})?$/

/** Quantity is valid: positive, or for adjustments any non-zero number with a sign. */
export function qtyOk(text: string, signed = false): boolean {
  return (signed ? SIGNED : QTY).test(text) && Number(text.replace(',', '.')) !== 0
}

export const newQtyLine = (item: ItemSummary): QtyLineDraft => ({
  item_id: item.id,
  label: `${item.name} (${item.sku})`,
  qty: '',
  unit_id: item.base_unit_id,
})
