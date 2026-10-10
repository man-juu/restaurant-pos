import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { PlanAcceptIn, PlanOut, PlanRow } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatNumber, intlLocale } from '../../lib/format'

const QTY = /^\d{1,14}([.,]\d{1,4})?$/
const valid = (v: string) => QTY.test(v) && Number(v.replace(',', '.')) > 0

function usePlanSuggestion(outletId: string, lang: string) {
  return useQuery({
    queryKey: ['production', 'plan', outletId, lang],
    queryFn: () =>
      request<PlanOut>(
        'GET',
        `/api/v1/production/plan?outlet_id=${outletId}&lang=${lang.slice(0, 2)}`,
      ),
  })
}

function useAccept() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ body, key }: { body: PlanAcceptIn; key: string }) =>
      request<unknown>('POST', '/api/v1/production/plan/accept', body, { 'Idempotency-Key': key }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['production'] }),
  })
}

/** FR-PRD-005: what to make in the coming days from par, branch requests and forecast use;
 * the chosen lines become planned production orders for the selected day. */
export function SuggestTab({
  outletId,
  date,
  canPlan,
}: {
  outletId: string
  date: string
  canPlan: boolean
}) {
  const { t, i18n } = useTranslation()
  const plan = usePlanSuggestion(outletId, i18n.language)
  const accept = useAccept()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [qty, setQty] = useState<Record<string, string>>({})
  const [off, setOff] = useState<Record<string, boolean>>({})
  const rows = plan.data?.rows ?? []
  const value = (r: PlanRow) => qty[r.item_id] ?? String(Number(r.suggested))
  const chosen = rows.filter((r) => !off[r.item_id])
  const ok = chosen.length > 0 && chosen.every((r) => valid(value(r)))
  const submit = () =>
    accept.mutate(
      {
        key,
        body: {
          outlet_id: outletId,
          production_date: date,
          lines: chosen.map((r) => ({ item_id: r.item_id, qty: value(r).replace(',', '.') })),
        },
      },
      { onSuccess: () => setKey(crypto.randomUUID()) },
    )
  return (
    <Card className="flex flex-col gap-3">
      <PlanNotes plan={plan.data} error={plan.error} />
      <ul className="flex flex-col gap-2">
        {rows.map((r) => (
          <SuggestLine
            key={r.item_id}
            row={r}
            locale={intlLocale(i18n.language)}
            qty={value(r)}
            on={!off[r.item_id]}
            onQty={(v) => setQty({ ...qty, [r.item_id]: v })}
            onToggle={(v) => setOff({ ...off, [r.item_id]: !v })}
            editable={canPlan}
          />
        ))}
      </ul>
      {accept.error ? <Alert>{errorMessage(accept.error, t)}</Alert> : null}
      {canPlan && rows.length > 0 && (
        <Button className="self-start" disabled={!ok || accept.isPending} onClick={submit}>
          {t('planning.accept', { count: chosen.length })}
        </Button>
      )}
    </Card>
  )
}

function SuggestLine(props: {
  row: PlanRow
  locale: string
  qty: string
  on: boolean
  editable: boolean
  onQty: (v: string) => void
  onToggle: (v: boolean) => void
}) {
  const { t } = useTranslation()
  const { row: r, locale } = props
  const f = (v: string | null | undefined) => formatNumber(Number(v ?? 0), locale)
  return (
    <li className="grid items-end gap-2 border-b border-line pb-2 sm:grid-cols-[auto_2fr_1fr]">
      {props.editable && <CheckInput label={r.name} checked={props.on} onChange={props.onToggle} />}
      <span className="text-sm text-ink-soft">
        {t('planning.planLine', {
          par: f(r.par_qty),
          have: f(r.on_hand),
          asked: f(r.requested),
          own: f(r.forecast_use),
          planned: f(r.planned),
          unit: r.unit_code,
        })}
        {r.can_make != null && Number(r.can_make) < Number(r.suggested) && (
          <span className="block text-danger">
            {t('planning.limited', { qty: f(r.can_make), unit: r.unit_code })}
          </span>
        )}
      </span>
      <TextInput
        label={t('planning.make', { unit: r.unit_code })}
        inputMode="decimal"
        disabled={!props.editable || !props.on}
        value={props.qty}
        onChange={(e) => props.onQty(e.target.value)}
      />
    </li>
  )
}

function PlanNotes({ plan, error }: { plan?: PlanOut; error: unknown }) {
  const { t } = useTranslation()
  if (error) return <Alert>{errorMessage(error, t)}</Alert>
  if (!plan) return null
  return (
    <p className="text-sm text-ink-soft">
      {plan.rows.length ? t('planning.planHelp', { days: plan.days }) : t('planning.planEmpty')}
    </p>
  )
}
