import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { CheckInput, SelectInput } from '../../components/form'
import { Alert } from '../../components/ui'
import type { Capabilities, TicketOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useOutlets } from '../../lib/session'
import { useNow } from '../tables/useFloorView'
import { useStations, useTickets } from './kitchenApi'
import { KitchenPrinter } from './KitchenPrinter'
import { StationSetup } from './StationSetup'
import { TicketCard } from './TicketCard'

const COLUMNS = ['new', 'preparing', 'ready'] as const

function useOutletPick() {
  const outlets = (useOutlets('kitchen').data ?? []).filter((o) => o.is_active)
  const [picked, setOutlet] = useState('')
  return { outlets, outletId: picked || outlets[0]?.id || '', setOutlet }
}

/** FR-KDS-001 to 004: the queue per station, oldest first; bump when served. */
export function KitchenPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const can = (code: string) => Boolean(caps?.permissions.includes(code))
  const { outlets, outletId, setOutlet } = useOutletPick()
  const stations = useStations(outletId).data ?? []
  const [stationId, setStation] = useState('')
  const [recall, setRecall] = useState(false)
  const tickets = useTickets(outletId, stationId, recall)
  const now = useNow()
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="mr-auto font-display text-3xl font-extrabold">{t('kitchen.title')}</h1>
        <SelectInput
          label={t('pos.outlet')}
          value={outletId}
          onChange={(e) => setOutlet(e.target.value)}
        >
          {outlets.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </SelectInput>
        <SelectInput
          label={t('kitchen.station')}
          value={stationId}
          onChange={(e) => setStation(e.target.value)}
        >
          <option value="">{t('kitchen.allStations')}</option>
          {stations.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </SelectInput>
        <CheckInput label={t('kitchen.recentlyBumped')} checked={recall} onChange={setRecall} />
      </div>
      <KitchenPrinter tickets={tickets.data ?? []} />
      {tickets.error && <Alert>{errorMessage(tickets.error, t)}</Alert>}
      {tickets.isSuccess && tickets.data.length === 0 && (
        <p className="text-ink-soft">{t('kitchen.empty')}</p>
      )}
      <TicketBoard
        tickets={tickets.data ?? []}
        recall={recall}
        now={now}
        canUpdate={can('kitchen.ticket.update')}
      />
      {can('kitchen.station.manage') && <StationSetup outletId={outletId} />}
    </div>
  )
}

function TicketBoard({
  tickets,
  recall,
  now,
  canUpdate,
}: {
  tickets: TicketOut[]
  recall: boolean
  now: number
  canUpdate: boolean
}) {
  const { t } = useTranslation()
  if (recall)
    return (
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {tickets.map((x) => (
          <TicketCard key={x.id} ticket={x} now={now} canUpdate={canUpdate} />
        ))}
      </div>
    )
  return (
    <div className="grid gap-4 md:grid-cols-3">
      {COLUMNS.map((col) => (
        <section key={col} className="flex flex-col gap-3" aria-label={t(`kitchen.columns.${col}`)}>
          <h2 className="font-display text-lg font-bold">{t(`kitchen.columns.${col}`)}</h2>
          {tickets
            .filter((x) => x.status === col)
            .map((x) => (
              <TicketCard key={x.id} ticket={x} now={now} canUpdate={canUpdate} />
            ))}
        </section>
      ))}
    </div>
  )
}
