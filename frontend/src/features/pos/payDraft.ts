import type { PaymentMethod, PosPayIn } from '../../lib/api/types'
import { parseMoney } from '../../lib/money'

/** One tender being typed: method code, what it pays of the bill, and cash handed over. */
export interface TenderDraft {
  method: string
  amount: string
  tendered: string
}

/** docs/05 rule 6.5, same as the server: round a cash bill half up to the step. */
export function cashRounding(total: number, step: number): number {
  if (step <= 1) return 0
  return Math.floor((2 * total + step) / (2 * step)) * step - total
}

export interface PayPlan {
  due: number
  rounding: number
  paid: number
  change: number
  body: PosPayIn | null // null while the tenders do not add up
}

interface Tender {
  method: string
  amount: number | null
  tendered: number | null
  cash: boolean
}

function parse(rows: TenderDraft[], kinds: Map<string, string>, currency: string, due: number) {
  return rows.map((r): Tender => ({
    method: r.method,
    // A single tender always pays the whole bill; the cashier types only cash received.
    amount: rows.length === 1 ? due : parseMoney(r.amount, currency),
    tendered: r.tendered.trim() === '' ? null : parseMoney(r.tendered, currency),
    cash: kinds.get(r.method) === 'cash',
  }))
}

const tenderOk = (t: Tender) =>
  t.amount !== null && t.amount > 0 && (!t.cash || t.tendered === null || t.tendered >= t.amount)

/** What the customer owes, the change, and the request body once everything adds up. */
export function payPlan(input: {
  total: number
  tip: number
  rows: TenderDraft[]
  methods: PaymentMethod[]
  roundingStep: number
  currency: string
}): PayPlan {
  const kinds = new Map(input.methods.map((m) => [m.code, m.kind]))
  const allCash = input.rows.length > 0 && input.rows.every((r) => kinds.get(r.method) === 'cash')
  const rounding = allCash ? cashRounding(input.total, input.roundingStep) : 0
  const due = input.total + rounding + input.tip
  const tenders = parse(input.rows, kinds, input.currency, due)
  const paid = tenders.reduce((sum, t) => sum + (t.amount ?? 0), 0)
  const change = tenders.reduce(
    (sum, t) =>
      sum +
      (t.cash && t.tendered !== null && t.amount !== null ? Math.max(0, t.tendered - t.amount) : 0),
    0,
  )
  const ok = tenders.length > 0 && tenders.every(tenderOk) && paid === due
  const body: PosPayIn | null = ok
    ? {
        tip: input.tip,
        payments: tenders.map((t) => ({
          method: t.method,
          amount: t.amount ?? 0,
          tendered: t.cash ? (t.tendered ?? t.amount) : null,
        })),
      }
    : null
  return { due, rounding, paid, change, body }
}

/** Quick cash buttons: the exact amount and the next round notes above it. */
export function quickCash(due: number, notes = [10_000, 20_000, 50_000, 100_000]): number[] {
  const ups = notes.map((n) => Math.ceil(due / n) * n).filter((v) => v > due)
  return [...new Set([due, ...ups])].slice(0, 4)
}
