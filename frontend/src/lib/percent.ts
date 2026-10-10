/**
 * Percent <-> basis points without floating-point maths (CLAUDE.md rule 5): the API stores
 * rates as integer basis points (1000 = 10 %). Accepts "10", "10.5", "10,5" (Indonesian
 * decimal comma) with at most two decimals.
 */
export function percentToBp(input: string): number | null {
  const match = /^\s*(\d{1,3})(?:[.,](\d{1,2}))?\s*$/.exec(input)
  if (!match) return null
  const whole = Number(match[1])
  const fraction = Number((match[2] ?? '').padEnd(2, '0'))
  const bp = whole * 100 + fraction
  return bp <= 10_000 ? bp : null
}

export function bpToPercent(bp: number, locale: string): string {
  const whole = Math.trunc(bp / 100)
  const fraction = bp % 100
  if (fraction === 0) return String(whole)
  const sep = locale.startsWith('id') ? ',' : '.'
  return `${whole}${sep}${String(fraction).padStart(2, '0').replace(/0$/, '')}`
}

/** For optional targets: empty is allowed (no target); otherwise above 0 and at most 100 %. */
export function optionalPercentOk(input: string): boolean {
  if (input.trim() === '') return true
  const bp = percentToBp(input)
  return bp !== null && bp > 0
}
