import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, StateBadge } from '../../components/ui'
import type { ReservationOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useBookingAction, useReservations } from './bookingApi'
import { ReservationForm } from './ReservationForm'
import { useNow } from './useFloorView'

const LATE_MIN = 15
const today = () => new Date().toLocaleDateString('sv') // YYYY-MM-DD in local time

type Props = {
  outletId: string
  channelId: string
  tableName: (id: string) => string
  canManage: boolean
}

/** FR-TBL-005, 007: the day's bookings; confirm, seat, mark no-show or cancel. */
export function ReservationsTab({ outletId, channelId, tableName, canManage }: Props) {
  const { t } = useTranslation()
  const [day, setDay] = useState(today)
  const [adding, setAdding] = useState(false)
  const list = useReservations(outletId, day)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2">
        <TextInput
          label={t('bookings.day')}
          type="date"
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
        {canManage && !adding && (
          <Button onClick={() => setAdding(true)}>{t('bookings.new')}</Button>
        )}
      </div>
      {adding && <ReservationForm outletId={outletId} day={day} onDone={() => setAdding(false)} />}
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('bookings.empty')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {list.data?.map((r) => (
          <ReservationRow
            key={r.id}
            r={r}
            channelId={channelId}
            tableName={tableName}
            canManage={canManage}
          />
        ))}
      </ul>
    </div>
  )
}

type RowProps = {
  r: ReservationOut
  channelId: string
  tableName: (id: string) => string
  canManage: boolean
}

function ReservationRow({ r, channelId, tableName, canManage }: RowProps) {
  const { t, i18n } = useTranslation()
  const now = useNow()
  const at = new Date(r.starts_at)
  const late = ['pending', 'confirmed'].includes(r.status) && now > at.getTime() + LATE_MIN * 60_000
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-line bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-bold">
            {t('bookings.line', {
              time: at.toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' }),
              name: r.guest_name,
              party: r.party_size,
            })}
          </p>
          <p className="text-sm text-muted">
            {r.table_ids.map(tableName).join(' + ')}
            {r.guest_phone ? ` · +${r.guest_phone}` : ''}
          </p>
          {r.no_shows > 0 && (
            <p className="text-sm text-danger">{t('bookings.noShows', { count: r.no_shows })}</p>
          )}
          {r.notes && <p className="text-sm">{r.notes}</p>}
        </div>
        <div className="flex gap-2">
          {late && <StateBadge state="late" label={t('bookings.late')} />}
          <StateBadge state={r.status} label={t(`bookings.status.${r.status}`)} />
        </div>
      </div>
      {canManage && <Actions r={r} channelId={channelId} />}
    </li>
  )
}

function Actions({ r, channelId }: { r: ReservationOut; channelId: string }) {
  const { t } = useTranslation()
  const act = useBookingAction()
  if (!['pending', 'confirmed'].includes(r.status)) return null
  const status = (s: string) =>
    act.mutate({ method: 'PUT', path: `reservations/${r.id}/status`, body: { status: s } })
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        disabled={act.isPending || !channelId}
        onClick={() =>
          act.mutate({
            method: 'POST',
            path: `reservations/${r.id}/seat`,
            body: { channel_id: channelId },
          })
        }
      >
        {t('bookings.seat')}
      </Button>
      {r.status === 'pending' && (
        <Button variant="ghost" disabled={act.isPending} onClick={() => status('confirmed')}>
          {t('bookings.confirm')}
        </Button>
      )}
      <Button variant="ghost" disabled={act.isPending} onClick={() => status('no_show')}>
        {t('bookings.noShow')}
      </Button>
      <Button variant="ghost" disabled={act.isPending} onClick={() => status('cancelled')}>
        {t('bookings.cancel')}
      </Button>
      {act.error && <Alert>{errorMessage(act.error, t)}</Alert>}
    </div>
  )
}
