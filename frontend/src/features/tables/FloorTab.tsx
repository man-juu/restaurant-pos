import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import type { Capabilities } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { FloorPlan } from './FloorPlan'
import { TableCard } from './TableCard'
import { TablePanel } from './TablePanel'
import { TableSetup } from './TableSetup'
import { type FloorView, useNow } from './useFloorView'

type Mode = 'list' | 'plan' | 'edit'

/** FR-TBL-001 to 004, 009: the tables of a floor as cards or as a plan; set up and lay out. */
export function FloorTab({ view, caps }: { view: FloorView; caps?: Capabilities }) {
  const { t, i18n } = useTranslation()
  const [selected, setSelected] = useState<string>()
  const [mode, setMode] = useState<Mode>('list')
  const now = useNow()
  const canSetup = Boolean(caps?.permissions.includes('tables.table.setup'))
  const money = (v: number) => formatMoney(v, caps?.currency ?? 'IDR', intlLocale(i18n.language))
  const current = view.all.find((x) => x.id === selected)
  const modes: Mode[] = canSetup ? ['list', 'plan', 'edit'] : ['list', 'plan']
  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-2" role="group" aria-label={t('tables.plan.view')}>
        {modes.map((m) => (
          <Button
            key={m}
            variant={mode === m ? 'primary' : 'ghost'}
            aria-pressed={mode === m}
            onClick={() => setMode(m)}
          >
            {t(`tables.plan.${m}`)}
          </Button>
        ))}
      </div>
      {view.tables.error && <Alert>{errorMessage(view.tables.error, t)}</Alert>}
      {view.tables.isSuccess && view.shown.length === 0 && (
        <p className="text-ink-soft">{t('tables.empty')}</p>
      )}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        {mode === 'list' ? (
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
        ) : (
          <FloorPlan
            tables={view.shown}
            editing={mode === 'edit'}
            selected={selected}
            onSelect={setSelected}
          />
        )}
        {current && mode !== 'edit' && (
          <TablePanel table={current} tables={view.all} channels={view.channels} money={money} />
        )}
      </div>
      {canSetup && <TableSetup outletId={view.outletId} floorId={view.floorId} />}
    </div>
  )
}
