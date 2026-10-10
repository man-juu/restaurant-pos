import { useTranslation } from 'react-i18next'

import { Alert, Button, Card, StateBadge } from '../../components/ui'
import type { DayOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { useLockDay } from './api'

/** The day's entries per channel, and the lock (FR-SAL-003). */
export function DaySummary({
  day,
  channels,
  currency,
  canLock,
}: {
  day: DayOut
  channels: Record<string, string>
  currency: string
  canLock: boolean
}) {
  const { t, i18n } = useTranslation()
  const lock = useLockDay()
  const locale = intlLocale(i18n.language)
  const locked = day.status === 'locked'
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-bold">{t('sales.dayTitle')}</h2>
        <StateBadge state={locked ? 'posted' : 'draft'} label={t(`sales.status.${day.status}`)} />
      </div>
      {day.documents.length === 0 && <p className="text-ink-soft">{t('sales.empty')}</p>}
      <ul className="flex flex-col gap-1 text-sm">
        {day.documents.map((d) => (
          <li key={d.id} className="flex flex-wrap justify-between gap-2">
            <span>
              {d.number} · {channels[d.channel_id] ?? ''}
            </span>
            <span className="tabular-nums">
              {formatMoney(d.total, currency, locale)}
              {d.discount > 0 &&
                ` · ${t('sales.promo', { value: formatMoney(d.discount, currency, locale) })}`}
            </span>
          </li>
        ))}
      </ul>
      {lock.error ? <Alert>{errorMessage(lock.error, t)}</Alert> : null}
      {canLock && (
        <Button
          variant="ghost"
          className="self-start"
          disabled={lock.isPending}
          onClick={() =>
            lock.mutate({ outletId: day.outlet_id, on: day.business_date, lock: !locked })
          }
        >
          {t(locked ? 'sales.reopen' : 'sales.lock')}
        </Button>
      )}
    </Card>
  )
}
