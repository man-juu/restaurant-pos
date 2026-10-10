import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, Tabs } from '../../components/form'
import type { Capabilities } from '../../lib/api/types'
import { FloorTab } from './FloorTab'
import { ReservationsTab } from './ReservationsTab'
import { type FloorView, useFloorView } from './useFloorView'
import { WaitlistTab } from './WaitlistTab'

const TABS = ['floor', 'reservations', 'waitlist'] as const
type Tab = (typeof TABS)[number]

/** FR-TBL-001 to 008: the floor, the day's reservations and the walk-in waitlist. */
export function TablesPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const view = useFloorView()
  const [tab, setTab] = useState<Tab>('floor')
  const canManage = Boolean(caps?.permissions.includes('tables.session.manage'))
  const channel = (view.channels.find((c) => c.kind === 'dine_in') ?? view.channels[0])?.id ?? ''
  const name = (id: string) => view.all.find((x) => x.id === id)?.name ?? ''
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="mr-auto font-display text-3xl font-extrabold">{t('tables.title')}</h1>
        <Pickers view={view} />
      </div>
      <Tabs tabs={TABS} value={tab} onChange={setTab} label={(k) => t(`bookings.tabs.${k}`)} />
      {tab === 'floor' && <FloorTab view={view} caps={caps} />}
      {tab === 'reservations' && (
        <ReservationsTab
          outletId={view.outletId}
          channelId={channel}
          tableName={name}
          canManage={canManage}
        />
      )}
      {tab === 'waitlist' && (
        <WaitlistTab
          outletId={view.outletId}
          channelId={channel}
          tables={view.all}
          canManage={canManage}
        />
      )}
    </div>
  )
}

function Pickers({ view }: { view: FloorView }) {
  const { t } = useTranslation()
  return (
    <>
      <SelectInput
        label={t('pos.outlet')}
        value={view.outletId}
        onChange={(e) => view.setOutlet(e.target.value)}
      >
        {view.outlets.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </SelectInput>
      <SelectInput
        label={t('tables.floor')}
        value={view.floorId}
        onChange={(e) => view.setFloor(e.target.value)}
      >
        {view.floors.map((f) => (
          <option key={f.id} value={f.id}>
            {f.name}
          </option>
        ))}
      </SelectInput>
    </>
  )
}
