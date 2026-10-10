import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { TableOut, WaitOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useBookingAction, useWaitlist } from './bookingApi'

type Props = { outletId: string; channelId: string; tables: TableOut[]; canManage: boolean }

/** FR-TBL-008: walk-ins waiting, with a rough wait; seat them at a free table. */
export function WaitlistTab({ outletId, channelId, tables, canManage }: Props) {
  const { t } = useTranslation()
  const list = useWaitlist(outletId)
  const act = useBookingAction()
  const [name, setName] = useState('')
  const [party, setParty] = useState('2')
  const add = () =>
    act.mutate(
      {
        method: 'POST',
        path: 'waitlist',
        body: { outlet_id: outletId, guest: { name: name.trim() }, party_size: Number(party) || 1 },
      },
      { onSuccess: () => setName('') },
    )
  const free = tables.filter((x) => x.is_active && x.status === 'available')
  return (
    <div className="flex flex-col gap-3">
      {canManage && (
        <Card className="flex flex-wrap items-end gap-2">
          <TextInput
            label={t('bookings.name')}
            value={name}
            maxLength={120}
            onChange={(e) => setName(e.target.value)}
          />
          <TextInput
            label={t('bookings.party')}
            inputMode="numeric"
            className="w-24"
            value={party}
            onChange={(e) => setParty(e.target.value)}
          />
          <Button onClick={add} disabled={!name.trim() || act.isPending}>
            {t('bookings.addWaiting')}
          </Button>
        </Card>
      )}
      {act.error && <Alert>{errorMessage(act.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('bookings.nobodyWaiting')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {list.data?.map((w) => (
          <WaitRow key={w.id} w={w} free={free} channelId={channelId} canManage={canManage} />
        ))}
      </ul>
    </div>
  )
}

function WaitRow({
  w,
  free,
  channelId,
  canManage,
}: {
  w: WaitOut
  free: TableOut[]
  channelId: string
  canManage: boolean
}) {
  const { t } = useTranslation()
  const act = useBookingAction()
  const fits = free.filter((x) => x.capacity >= w.party_size)
  const [table, setTable] = useState('')
  const chosen = table || fits[0]?.id || ''
  return (
    <li className="flex flex-wrap items-end justify-between gap-2 rounded-xl border border-line bg-card p-3">
      <div>
        <p className="font-bold">
          {t('bookings.waitLine', { name: w.guest_name, party: w.party_size })}
        </p>
        <p className="text-sm text-muted">{t('bookings.wait', { count: w.estimated_wait_min })}</p>
      </div>
      {canManage && (
        <div className="flex flex-wrap items-end gap-2">
          {fits.length > 0 && (
            <SelectInput
              label={t('bookings.table')}
              value={chosen}
              onChange={(e) => setTable(e.target.value)}
            >
              {fits.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </SelectInput>
          )}
          <Button
            disabled={!chosen || !channelId || act.isPending}
            onClick={() =>
              act.mutate({
                method: 'POST',
                path: `waitlist/${w.id}/seat`,
                body: { table_ids: [chosen], channel_id: channelId },
              })
            }
          >
            {t('bookings.seat')}
          </Button>
          <Button
            variant="ghost"
            disabled={act.isPending}
            onClick={() => act.mutate({ method: 'POST', path: `waitlist/${w.id}/leave` })}
          >
            {t('bookings.left')}
          </Button>
        </div>
      )}
      {act.error && <Alert>{errorMessage(act.error, t)}</Alert>}
    </li>
  )
}
