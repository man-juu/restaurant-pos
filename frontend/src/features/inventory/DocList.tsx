import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { StateBadge } from '../../components/ui'
import type { StockDocument } from '../../lib/api/types'
import { formatDate, intlLocale } from '../../lib/format'

const BADGE: Record<string, string> = {
  posted: 'active',
  submitted: 'expiring',
  draft: 'read_only',
  rejected: 'suspended',
  reversed: 'suspended',
}

/** Recent documents of one kind; `actions` renders the buttons a row offers. */
export function DocList({
  docs,
  actions,
}: {
  docs: StockDocument[]
  actions?: (doc: StockDocument) => ReactNode
}) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  if (docs.length === 0) return <p className="text-ink-soft">{t('inventory.docs.none')}</p>
  return (
    <ul className="flex flex-col gap-2">
      {docs.map((d) => (
        <li
          key={d.id}
          className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-card px-3 py-2"
        >
          <span>
            <b>{d.number}</b>{' '}
            <span className="text-sm text-ink-soft">
              {formatDate(d.business_date, locale)}
              {d.reason_code && ` · ${t(`inventory.reasons.${d.reason_code}`)}`}
              {d.count_type && ` · ${t(`inventory.countTypes.${d.count_type}`)}`}
            </span>
          </span>
          <span className="flex flex-wrap items-center gap-2">
            <StateBadge
              state={BADGE[d.status] ?? 'read_only'}
              label={t(`inventory.status.${d.status}`)}
            />
            {actions?.(d)}
          </span>
        </li>
      ))}
    </ul>
  )
}
