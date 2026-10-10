/** Quick purchase form state -> API body. Quantities stay exact decimal strings. */
import type { QuickPurchaseIn } from '../../lib/api/types'
import { parseMoney } from '../../lib/money'

export interface QuickLineDraft {
  item_id: string
  label: string
  qty: string
  unit_id: string
  total: string // what was paid for the line, as typed
  expiry: string // '' = filled from the shelf life by the server
}

const QTY = /^\d{1,14}([.,]\d{1,4})?$/

export const lineInvalid = (ln: QuickLineDraft, currency: string) =>
  !QTY.test(ln.qty) ||
  Number(ln.qty.replace(',', '.')) <= 0 ||
  !ln.unit_id ||
  parseMoney(ln.total, currency) === null

export const quickTotal = (lines: QuickLineDraft[], currency: string) =>
  lines.reduce((sum, ln) => sum + (parseMoney(ln.total, currency) ?? 0), 0)

export function toQuickBody(
  form: { outletId: string; vendorId: string; vendorName: string; date: string; invoice?: string },
  lines: QuickLineDraft[],
  currency: string,
): QuickPurchaseIn {
  return {
    outlet_id: form.outletId,
    vendor_id: form.vendorId || null,
    vendor_name: form.vendorId ? null : form.vendorName.trim() || null,
    business_date: form.date,
    invoice_upload_id: form.invoice ?? null,
    lines: lines.map((ln) => ({
      item_id: ln.item_id,
      qty: ln.qty.replace(',', '.'),
      unit_id: ln.unit_id,
      line_total: parseMoney(ln.total, currency) ?? 0,
      expiry_date: ln.expiry || null,
    })),
  }
}
