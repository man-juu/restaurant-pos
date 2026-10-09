import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput } from '../../components/form'
import { Alert } from '../../components/ui'
import type { Capabilities } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { TableCard } from './TableCard'
import { TablePanel } from './TablePanel'
import { TableSetup } from './TableSetup'
import { type FloorView, useFloorView, useNow } from './useFloorView'

/** FR-TBL-001 to 004: the floor with every table's state; tap one to act on it. */
export function TablesPage() {
  const { t, i18n } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const view = useFloorView()
  const [selected, setSelected] = useState<string>()
  const now = useNow()
  const money = (v: number) => formatMoney(v, caps?.currency ?? 'IDR', intlLocale(i18n.language))
  const current = view.all.find((x) => x.id === selected)
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <h1 className="mr-auto font-display text-3xl font-extrabold">{t('tables.title')}</h1>
        <Pickers view={view} />
      </div>
      {view.tables.error && <Alert>{errorMessage(view.tables.error, t)}</Alert>}
      {view.tables.isSuccess && view.shown.length === 0 && (
        <p className="text-ink-soft">{t('tables.empty')}</p>
      )}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
          {view.shown.map((x) => (
            <li key={x.id}>
              <TableCard
                table={x}
                selected={x.id === selected}
                money={money}
                now={now}
                onSelect={() => setSelected(x.id)}
              />
            </li>
          ))}
        </ul>
        {current && (
          <TablePanel table={current} tables={view.all} channels={view.channels} money={money} />
        )}
      </div>
      {caps?.permissions.includes('tables.table.setup') && (
        <TableSetup outletId={view.outletId} floorId={view.floorId} />
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
