/**
 * Typed money -> integer minor units (CLAUDE.md rule 5: never floats). Returns null when the
 * text is not a valid amount, so the form can block saving.
 *
 * Currencies without minor units (IDR): "25.000", "25,000", "25 000" and "25000" all mean
 * 25000; separators are only grouping. Others: one optional "." or "," decimal mark with at
 * most the currency's digits, no grouping ("12.5" -> 1250).
 */
import { minorDigits } from './format'

const MAX_MINOR = 10 ** 12 // same limit as the API

export function parseMoney(text: string, currency: string): number | null {
  const digits = minorDigits(currency)
  const value = text.trim()
  if (digits === 0) {
    const plain = value.replace(/[.,\s]/g, '')
    return /^\d{1,13}$/.test(plain) ? within(Number(plain)) : null
  }
  const match = new RegExp(`^(\\d{1,13})(?:[.,](\\d{1,${digits}}))?$`).exec(value)
  if (!match) return null
  const fraction = (match[2] ?? '').padEnd(digits, '0')
  return within(Number(match[1]) * 10 ** digits + Number(fraction))
}

const within = (minor: number): number | null => (minor <= MAX_MINOR ? minor : null)
