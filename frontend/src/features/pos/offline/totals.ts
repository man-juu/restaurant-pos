import type { OfflinePackOut } from '../../../lib/api/types'

/** The server's document totals (backend app/core/settings/pricing.py), so a till without a
 * connection shows the same total the server will post: integers only, half-up rounding
 * once per tax, inclusive taxes split out of the price. Keep the two in step. */

const BP = 10_000

export function roundHalfUpDiv(n: number, d: number): number {
  const sign = n < 0 !== d < 0 ? -1 : 1
  const a = Math.abs(n)
  const b = Math.abs(d)
  return sign * Math.floor((2 * a + b) / (2 * b))
}

export interface OfflineTotals {
  subtotal: number
  serviceCharge: number
  tax: number
  total: number
}

type Rules = Pick<OfflinePackOut, 'tax' | 'service_charge' | 'channel_code'>

function applicable(rules: Rules['tax']['rules'], outletId: string) {
  return (rules ?? [])
    .filter((r) => r.active !== false && (r.outlet_ids == null || r.outlet_ids.includes(outletId)))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.id.localeCompare(b.id))
}

function inclusiveSplit(gross: number, rates: number[]) {
  const net = roundHalfUpDiv(gross * BP, BP + rates.reduce((s, r) => s + r, 0))
  const amounts = rates.map((r) => roundHalfUpDiv(net * r, BP))
  if (rates.length > 0) {
    const largest = rates.indexOf(Math.max(...rates))
    amounts[largest] += gross - net - amounts.reduce((s, a) => s + a, 0)
  }
  return { net, tax: amounts.reduce((s, a) => s + a, 0) }
}

export function offlineTotals(lineTotals: number[], pack: Rules, outletId: string): OfflineTotals {
  const gross = lineTotals.reduce((s, x) => s + x, 0)
  const rules = applicable(pack.tax.rules, outletId)
  const inclusive = rules.filter((r) => r.price_includes_tax)
  const { net, tax: inTax } = inclusiveSplit(
    gross,
    inclusive.map((r) => r.rate_bp),
  )
  const sc = pack.service_charge
  const scOn =
    Boolean(sc.enabled) && (!sc.channels?.length || sc.channels.includes(pack.channel_code))
  const service = scOn ? roundHalfUpDiv(net * (sc.rate_bp ?? 0), BP) : 0
  const exTax = rules
    .filter((r) => !r.price_includes_tax)
    .reduce((s, r) => {
      const withSc = r.applies_to_service_charge !== false && sc.before_tax !== false
      return s + roundHalfUpDiv((net + (withSc ? service : 0)) * r.rate_bp, BP)
    }, 0)
  return {
    subtotal: gross,
    serviceCharge: service,
    tax: inTax + exTax,
    total: net + service + inTax + exTax,
  }
}
