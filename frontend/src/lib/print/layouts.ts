import type { TFunction } from 'i18next'

import type { SaleReceiptOut, TicketOut } from '../api/types'
import { COLUMNS, Receipt } from './escpos'

type Money = (minor: number) => string

const nonEmpty = (text: string | null | undefined) => (text ?? '').split('\n').filter(Boolean)

function head(p: Receipt, r: SaleReceiptOut, t: TFunction): void {
  p.center(true).bold(true).line(r.business).bold(false).line(r.outlet)
  for (const part of [...nonEmpty(r.address), ...nonEmpty(r.header)]) p.line(part)
  p.center(false).rule().pair(r.number, r.at)
  if (r.label) p.line(r.label)
  p.line(`${t('receipt.cashier')}: ${r.cashier}`)
  if (!r.paid) p.bold(true).line(t('receipt.bill')).bold(false)
  p.rule()
}

function items(p: Receipt, r: SaleReceiptOut, t: TFunction, money: Money): void {
  for (const ln of r.lines) {
    p.pair(`${Number(ln.qty)} x ${ln.name}`, money(ln.total))
    for (const m of ln.modifiers) p.line(`  + ${m}`)
    if (ln.discount) p.pair(`  ${t('receipt.discount')}`, `-${money(ln.discount)}`)
  }
}

function sums(p: Receipt, r: SaleReceiptOut, t: TFunction, money: Money): void {
  p.rule().pair(t('receipt.subtotal'), money(r.subtotal))
  const parts: [string, number][] = [
    ['receipt.discount', -r.discount],
    ['receipt.service', r.service_charge],
    ['receipt.tax', r.tax],
    ['receipt.rounding', r.rounding],
    ['receipt.tip', r.tip],
  ]
  for (const [key, value] of parts.filter(([, v]) => v !== 0)) p.pair(t(key), money(value))
  p.bold(true).pair(t('receipt.total'), money(r.total)).bold(false)
  for (const pay of r.payments) {
    p.pair(pay.method, money(pay.tendered ?? pay.amount))
    if (pay.change) p.pair(t('receipt.change'), money(pay.change))
  }
}

/** FR-SAL-010: the receipt as ESC/POS bytes; same content as the PDF. */
export function receiptBytes(r: SaleReceiptOut, t: TFunction, money: Money): Uint8Array {
  const p = new Receipt(COLUMNS[r.paper_mm] ?? 32)
  head(p, r, t)
  items(p, r, t, money)
  sums(p, r, t, money)
  p.center(true)
  for (const part of nonEmpty(r.footer)) p.line(part)
  return p.cut()
}

/** FR-KDS-002: a station ticket, big and plain, no prices. */
export function ticketBytes(k: TicketOut, t: TFunction, paperMm = 58): Uint8Array {
  const p = new Receipt(COLUMNS[paperMm] ?? 32)
  p.bold(true)
    .line(k.label ?? k.order_number)
    .bold(false)
  p.line(`${k.order_number} ${k.channel_name}${k.platform ? ` (${k.platform})` : ''}`)
  p.line(new Date(k.created_at).toLocaleTimeString()).rule()
  for (const i of k.items) {
    if (i.status === 'void') {
      p.line(`${t('receipt.void')}: ${Number(i.qty)} x ${i.name}`)
      continue
    }
    p.bold(true)
      .line(`${Number(i.qty)} x ${i.name}`)
      .bold(false)
    if (i.modifiers) p.line(`  ${i.modifiers}`)
    if (i.note) p.line(`  ! ${i.note}`)
  }
  return p.cut()
}
