import { clsx } from 'clsx'
import { useTranslation } from 'react-i18next'

import { StateBadge } from '../../components/ui'
import type { TableOut } from '../../lib/api/types'

const minutesSince = (iso: string, now: number) =>
  Math.max(0, Math.floor((now - new Date(iso).getTime()) / 60_000))

/** FR-TBL-004: one table on the floor with status, time seated and open amount. */
export function TableCard({
  table,
  selected,
  money,
  now,
  onSelect,
}: {
  table: TableOut
  selected: boolean
  money: (v: number) => string
  now: number
  onSelect: () => void
}) {
  const { t } = useTranslation()
  const session = table.session
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={onSelect}
      className={clsx(
        'flex min-h-28 w-full flex-col gap-1 rounded-xl border bg-card p-3 text-left hover:bg-raised',
        selected ? 'border-accent ring-2 ring-accent' : 'border-line',
      )}
    >
      <span className="flex items-center justify-between gap-2">
        <b className="text-lg">{table.name}</b>
        <span className="text-sm text-ink-soft">
          {t('tables.seats', { count: table.capacity })}
        </span>
      </span>
      <StateBadge state={table.status} label={t(`tables.status.${table.status}`)} />
      {session && (
        <span className="text-sm tabular-nums">
          {t('tables.seated', {
            minutes: minutesSince(session.opened_at, now),
            party: session.party_size,
          })}
          <br />
          <b>{money(session.open_amount)}</b>
        </span>
      )}
    </button>
  )
}
