import type { MenuItemOut, OfflineOrderIn, OfflinePackOut } from '../../../lib/api/types'
import { payPlan } from '../payDraft'
import { offlineTotals } from './totals'

export interface CartLine {
  key: string
  item: MenuItemOut
  optionIds: string[]
  note: string
  qty: number
}

/** Price shown on the till; the server prices the order again when it arrives. */
export function linePrice(line: CartLine): number {
  const options = line.item.modifier_groups.flatMap((g) => g.options)
  const extras = options
    .filter((o) => line.optionIds.includes(o.id))
    .reduce((s, o) => s + o.price_delta, 0)
  return (line.item.price + extras) * line.qty
}

export function addToCart(lines: CartLine[], line: Omit<CartLine, 'key' | 'qty'>): CartLine[] {
  const same = (l: CartLine) =>
    l.item.id === line.item.id &&
    l.note === line.note &&
    l.optionIds.join() === line.optionIds.join()
  if (lines.some(same)) return lines.map((l) => (same(l) ? { ...l, qty: l.qty + 1 } : l))
  return [...lines, { ...line, key: crypto.randomUUID(), qty: 1 }]
}

export function changeQty(lines: CartLine[], key: string, by: number): CartLine[] {
  return lines.map((l) => (l.key === key ? { ...l, qty: l.qty + by } : l)).filter((l) => l.qty > 0)
}

interface Checkout {
  lines: CartLine[]
  pack: OfflinePackOut
  outletId: string
  method: string | null // null: served now, paid later on the server
  tendered: string
  currency: string
}

/** The total the customer sees and the upload body, or no body while the cash is short. */
export function checkout(c: Checkout) {
  const totals = offlineTotals(c.lines.map(linePrice), c.pack, c.outletId)
  const plan = c.method
    ? payPlan({
        total: totals.total,
        tip: 0,
        rows: [{ method: c.method, amount: '', tendered: c.tendered }],
        methods: c.pack.methods,
        roundingStep: c.pack.cash_rounding_step,
        currency: c.currency,
      })
    : null
  return { totals, plan, ready: c.lines.length > 0 && (plan === null || plan.body !== null) }
}

export function orderBody(
  c: Checkout & { channelId: string; payment: OfflineOrderIn['payment'] },
): OfflineOrderIn {
  return {
    client_id: crypto.randomUUID(),
    outlet_id: c.outletId,
    channel_id: c.channelId,
    taken_at: new Date().toISOString(),
    lines: c.lines.map((l) => ({
      item_id: l.item.id,
      qty: String(l.qty),
      option_ids: l.optionIds,
      note: l.note.trim() || null,
    })),
    payment: c.payment,
  }
}
