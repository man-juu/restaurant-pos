import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button } from '../../components/ui'
import type { ProductionOut } from '../../lib/api/types'
import { ApiError } from '../../lib/api/client'
import { errorMessage } from '../../lib/errors'
import { useComplete } from './api'
import { QTY } from './PlanForm'

const dot = (v: string) => v.replace(',', '.')

/** FR-PRD-002, 003: what really came out, and what was used if it differs from the recipe. */
export function CompleteForm({ order }: { order: ProductionOut }) {
  const { t } = useTranslation()
  const complete = useComplete()
  const [actual, setActual] = useState(String(Number(order.planned_qty)))
  const [used, setUsed] = useState<Record<string, string>>({})
  const short = complete.error instanceof ApiError && complete.error.code === 'insufficient_stock'
  const changed = Object.entries(used).filter(([, v]) => QTY.test(v) || v === '0')
  const ok = QTY.test(actual) && Number(dot(actual)) > 0
  const submit = (confirm: boolean) =>
    complete.mutate({
      id: order.id,
      body: {
        actual_qty: dot(actual),
        used: changed.map(([item_id, qty]) => ({ item_id, qty: dot(qty) })),
        confirm_negative: confirm,
      },
    })
  return (
    <div className="flex flex-col gap-3 border-t border-line pt-3">
      <h3 className="font-bold">{t('production.complete')}</h3>
      <TextInput
        label={t('production.actualQty', { unit: order.unit_code })}
        inputMode="decimal"
        value={actual}
        onChange={(e) => setActual(e.target.value)}
      />
      {order.lines.map((ln) => (
        <TextInput
          key={ln.item_id}
          label={t('production.used', { name: ln.item_name, unit: ln.unit_code })}
          inputMode="decimal"
          placeholder={String(Number(ln.planned_qty))}
          value={used[ln.item_id] ?? ''}
          onChange={(e) => setUsed({ ...used, [ln.item_id]: e.target.value })}
        />
      ))}
      {complete.error ? <Alert>{errorMessage(complete.error, t)}</Alert> : null}
      <div className="flex flex-wrap gap-2">
        <Button disabled={!ok || complete.isPending} onClick={() => submit(false)}>
          {t('production.completeSave')}
        </Button>
        {short && (
          <Button variant="ghost" onClick={() => submit(true)}>
            {t('production.completeAnyway')}
          </Button>
        )}
      </div>
    </div>
  )
}
