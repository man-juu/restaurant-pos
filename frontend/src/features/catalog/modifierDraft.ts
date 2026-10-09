import type { ModifierOptionIn } from '../../lib/api/types'

export const MONEY = /^-?\d{1,13}$/
export const DELTA = /^-?\d{1,14}([.,]\d{1,4})?$/

/** The ingredient change must be a non-zero number; the price change a whole amount. */
export function optionValid(o: ModifierOptionIn): boolean {
  if (o.name.trim() === '' || !MONEY.test(String(o.price_delta ?? 0))) return false
  if (!o.ingredient_item_id) return true
  const qty = String(o.ingredient_qty ?? '')
  return DELTA.test(qty) && Number(qty.replace(',', '.')) !== 0
}
