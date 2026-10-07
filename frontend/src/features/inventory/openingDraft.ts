/** Opening stock form state -> API body. Quantities stay exact decimal strings. */
import type { OpeningIn } from '../../lib/api/types'
import { parseMoney } from '../../lib/money'

export interface OpeningLineDraft {
  item_id: string
  label: string
  qty: string
  unit_id: string
  cost: string // per unit, as typed
  lot: string
  expiry: string // YYYY-MM-DD or ''
}

const QTY = /^\d{1,14}([.,]\d{1,4})?$/

export function lineProblem(ln: OpeningLineDraft, currency: string): boolean {
  const qtyOk = QTY.test(ln.qty) && Number(ln.qty.replace(',', '.')) > 0
  return !qtyOk || !ln.unit_id || parseMoney(ln.cost, currency) === null
}

export function toOpeningBody(
  outletId: string,
  businessDate: string,
  lines: OpeningLineDraft[],
  currency: string,
): OpeningIn {
  return {
    outlet_id: outletId,
    business_date: businessDate,
    lines: lines.map((ln) => ({
      item_id: ln.item_id,
      qty: ln.qty.replace(',', '.'),
      unit_id: ln.unit_id,
      unit_cost: String(parseMoney(ln.cost, currency) ?? 0),
      lot_code: ln.lot.trim() || null,
      expiry_date: ln.expiry || null,
    })),
  }
}
