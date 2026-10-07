/**
 * Locale formatting (FR-X-002). Money is integer minor units from the API; IDR has none, so
 * 25000 means Rp 25.000. Times are stored in UTC and shown in the outlet's timezone.
 */

const MINOR_DIGITS: Record<string, number> = { IDR: 0, JPY: 0 }

export function formatMoney(minor: number, currency: string, locale: string): string {
  const digits = MINOR_DIGITS[currency] ?? 2
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(minor / 10 ** digits)
}

export function formatNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value)
}

export function formatDateTime(iso: string, locale: string, timeZone: string): string {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone,
  }).format(new Date(iso))
}

/** i18next language code -> Intl locale. */
export function intlLocale(language: string): string {
  return language === 'id' ? 'id-ID' : 'en-GB'
}
