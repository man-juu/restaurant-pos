// Option lists shared by the catalog screens (values match the API enums).
export const ITEM_TYPES = ['menu', 'semi_finished', 'ingredient'] as const
export const STORAGE_TYPES = ['frozen', 'chilled', 'dry'] as const
export const UNIT_DIMENSIONS = ['mass', 'volume', 'count'] as const
export const CHANNEL_KINDS = ['dine_in', 'takeaway', 'platform', 'wholesale'] as const

/** Today in the browser's time zone as YYYY-MM-DD (the default start date of a new price). */
export function todayIso(now = new Date()): string {
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}
