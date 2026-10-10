import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../../components/form'
import { Alert, Button, Card } from '../../../components/ui'
import { request } from '../../../lib/api/client'
import { errorMessage } from '../../../lib/errors'
import { parseMoney } from '../../../lib/money'
import { todayIso } from '../../catalog/labels'
import type { BudgetProps } from './BudgetTab'

const FIELDS = ['net_sales', 'cost_of_sales', 'labor', 'expenses'] as const
type Field = (typeof FIELDS)[number]
const EMPTY: Record<Field, string> = { net_sales: '', cost_of_sales: '', labor: '', expenses: '' }

/** Saving the same outlet and month again replaces the plan (audited on the server). */
export function BudgetForm({ outletId, currency }: BudgetProps) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [month, setMonth] = useState(todayIso().slice(0, 7))
  const [values, setValues] = useState(EMPTY)
  const amounts = FIELDS.map((f) => parseMoney(values[f] || '0', currency))
  const save = useMutation({
    mutationFn: () =>
      request<void>('PUT', '/api/v1/finance/budgets', {
        outlet_id: outletId,
        month: `${month}-01`,
        ...Object.fromEntries(FIELDS.map((f, i) => [f, amounts[i] ?? 0])),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['budget'] }),
  })
  const ok = /^\d{4}-\d{2}$/.test(month) && amounts.every((a) => a !== null)
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-bold">{t('budget.enter')}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput
          label={t('budget.month')}
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
        />
        {FIELDS.map((f) => (
          <TextInput
            key={f}
            label={`${t(`budget.lines.${f}`)} (${currency})`}
            inputMode="numeric"
            value={values[f]}
            onChange={(e) => setValues({ ...values, [f]: e.target.value })}
          />
        ))}
      </div>
      <p className="text-sm text-muted">{t('budget.help')}</p>
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      {save.isSuccess && <p className="text-sm text-good">{t('budget.saved')}</p>}
      <Button className="self-start" disabled={!ok || save.isPending} onClick={() => save.mutate()}>
        {t('budget.save')}
      </Button>
    </Card>
  )
}
