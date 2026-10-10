import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { ItemSummary } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { ComponentPicker } from '../catalog/ComponentPicker'
import { usePlan } from './api'

export const QTY = /^\d{1,14}([.,]\d{1,4})?$/
const OUTPUT_TYPES = ['semi_finished'] as const

/** FR-PRD-001: what to make, how much and on which day; components come from the recipe. */
export function PlanForm({ outletId, date }: { outletId: string; date: string }) {
  const { t } = useTranslation()
  const plan = usePlan()
  const [item, setItem] = useState<ItemSummary>()
  const [qty, setQty] = useState('')
  const [key, setKey] = useState(() => crypto.randomUUID())
  const ok = item && QTY.test(qty) && Number(qty.replace(',', '.')) > 0
  const submit = () =>
    item &&
    plan.mutate(
      {
        body: {
          outlet_id: outletId,
          item_id: item.id,
          planned_qty: qty.replace(',', '.'),
          production_date: date,
        },
        key,
      },
      { onSuccess: () => (setItem(undefined), setQty(''), setKey(crypto.randomUUID())) },
    )
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-bold">{t('production.plan')}</h2>
      {item ? (
        <p className="font-semibold">{item.name}</p>
      ) : (
        <ComponentPicker
          exclude={new Set()}
          onPick={setItem}
          label={t('production.what')}
          types={OUTPUT_TYPES}
        />
      )}
      <TextInput
        label={t('production.plannedQty')}
        inputMode="decimal"
        value={qty}
        onChange={(e) => setQty(e.target.value)}
      />
      {plan.error ? <Alert>{errorMessage(plan.error, t)}</Alert> : null}
      <Button className="self-start" disabled={!ok || plan.isPending} onClick={submit}>
        {t('production.planSave')}
      </Button>
    </Card>
  )
}
