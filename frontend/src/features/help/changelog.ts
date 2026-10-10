/** FR-X-007: what changed, newest first. Text lives in the locale files under
 * `changelog.<id>`; add an entry with each release. */
export const CHANGELOG = [
  { id: '2026-10-10i', date: '2026-10-10' }, // online booking
  { id: '2026-10-10h', date: '2026-10-10' }, // loyalty
  { id: '2026-10-10g', date: '2026-10-10' }, // budgets
  { id: '2026-10-10f', date: '2026-10-10' }, // platform sales files
  { id: '2026-10-10e', date: '2026-10-10' }, // offline till
  { id: '2026-10-10d', date: '2026-10-10' }, // modules per outlet, simple finance
  { id: '2026-10-10c', date: '2026-10-10' }, // exports, announcements, push, help
  { id: '2026-10-10b', date: '2026-10-10' }, // transfers, menu engineering, prime cost
  { id: '2026-10-10a', date: '2026-10-10' }, // books, receivables, platforms, stock depth
  { id: '2026-10-09', date: '2026-10-09' }, // tables, POS depth, vendor bills
] as const

const SEEN_KEY = 'changelog-seen'

export const latestId = CHANGELOG[0].id

/** Per-device convenience only: storage may be missing (private mode), so failures are ok. */
export function seenLatest(): boolean {
  try {
    return localStorage.getItem(SEEN_KEY) === latestId
  } catch {
    return true
  }
}

export function markSeen(): void {
  try {
    localStorage.setItem(SEEN_KEY, latestId)
  } catch {
    /* nothing to remember without storage */
  }
}
