import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput } from '../../components/form'
import { Alert, Button } from '../../components/ui'
import type { TableOut, TableSessionOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { SplitBill } from './SplitBill'
import { useSessionStep } from './tablesApi'

/** Move the party, join another party, add a bill, or split items to a new bill. */
export function SessionActions({
  session,
  table,
  tables,
}: {
  session: TableSessionOut
  table: TableOut
  tables: TableOut[]
}) {
  const { t } = useTranslation()
  const step = useSessionStep(session.id)
  const [target, setTarget] = useState('')
  const [splitting, setSplitting] = useState(false)
  const free = tables.filter((x) => x.status === 'available' && x.is_active)
  const others = tables.filter((x) => x.session && x.session.id !== session.id)
  const pick = tables.find((x) => x.id === target)
  return (
    <div className="flex flex-col gap-2 border-t border-line pt-3">
      <SelectInput
        label={t('tables.otherTable')}
        value={target}
        onChange={(e) => setTarget(e.target.value)}
      >
        <option value="">{t('tables.choose')}</option>
        {[...free, ...others]
          .filter((x) => x.id !== table.id)
          .map((x) => (
            <option key={x.id} value={x.id}>
              {x.name} · {t(`tables.status.${x.status}`)}
            </option>
          ))}
      </SelectInput>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="ghost"
          disabled={pick?.status !== 'available'}
          onClick={() => pick && step.mutate({ kind: 'move', to_table_id: pick.id })}
        >
          {t('tables.move')}
        </Button>
        <Button
          variant="ghost"
          disabled={!pick?.session}
          onClick={() =>
            pick?.session && step.mutate({ kind: 'merge', session_id: pick.session.id })
          }
        >
          {t('tables.merge')}
        </Button>
        <Button variant="ghost" onClick={() => step.mutate({ kind: 'orders' })}>
          {t('tables.newBill')}
        </Button>
        <Button variant="ghost" onClick={() => setSplitting(!splitting)}>
          {t('tables.split')}
        </Button>
      </div>
      {step.error ? <Alert>{errorMessage(step.error, t)}</Alert> : null}
      {splitting && <SplitBill session={session} onDone={() => setSplitting(false)} />}
    </div>
  )
}
