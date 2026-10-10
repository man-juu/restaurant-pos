import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import type { OutletOut, StandingOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatDate, intlLocale } from '../../lib/format'
import { useRunStanding, useStanding } from './standingApi'
import { StandingForm } from './StandingForm'

/** FR-TRF-005: standing orders to and from this outlet; requests are made automatically. */
export function StandingTab({
  outletId,
  outlets,
  canRequest,
}: {
  outletId: string
  outlets: OutletOut[]
  canRequest: boolean
}) {
  const { t, i18n } = useTranslation()
  const list = useStanding(outletId, i18n.language)
  const run = useRunStanding()
  const [editing, setEditing] = useState<StandingOut | 'new'>()
  const names = Object.fromEntries(outlets.map((o) => [o.id, o.name]))
  if (editing)
    return (
      <StandingForm
        outletId={outletId}
        outlets={outlets}
        current={editing === 'new' ? undefined : editing}
        onDone={() => setEditing(undefined)}
      />
    )
  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-ink-soft">{t('standing.help')}</p>
      {canRequest && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setEditing('new')}>{t('standing.new')}</Button>
          <Button variant="ghost" disabled={run.isPending} onClick={() => run.mutate()}>
            {t('standing.runNow')}
          </Button>
        </div>
      )}
      {run.isSuccess && <p className="text-sm">{t('standing.made', { count: run.data.made })}</p>}
      {(list.error ?? run.error) ? <Alert>{errorMessage(list.error ?? run.error, t)}</Alert> : null}
      {list.data?.map((s) => (
        <Row
          key={s.id}
          s={s}
          names={names}
          onEdit={canRequest && s.to_outlet_id === outletId ? () => setEditing(s) : undefined}
        />
      ))}
    </div>
  )
}

function Row({
  s,
  names,
  onEdit,
}: {
  s: StandingOut
  names: Record<string, string>
  onEdit?: () => void
}) {
  const { t, i18n } = useTranslation()
  return (
    <Card className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <p className="font-bold">{`${names[s.from_outlet_id] ?? ''} → ${names[s.to_outlet_id] ?? ''}`}</p>
        <p className="text-sm text-ink-soft">
          {t('standing.line', {
            days: s.weekdays.map((d) => t(`standing.weekday.${d}`)).join(', '),
            lead: s.lead_days,
            items: s.lines.length,
          })}
        </p>
        <p className="text-sm text-muted">
          {s.next_delivery
            ? t('standing.next', { date: formatDate(s.next_delivery, intlLocale(i18n.language)) })
            : t('standing.off')}
        </p>
      </div>
      {onEdit && (
        <Button variant="ghost" onClick={onEdit}>
          {t('standing.edit')}
        </Button>
      )}
    </Card>
  )
}
