import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { PrimeCostOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { parseMoney } from '../../lib/money'
import { todayIso } from '../catalog/labels'

type Props = { outletId: string; from: string; to: string; currency: string; canEnter: boolean }

function usePrime({ outletId, from, to }: Props) {
  return useQuery({
    queryKey: ['prime', outletId, from, to],
    queryFn: () =>
      request<PrimeCostOut>(
        'GET',
        `/api/v1/finance/prime-cost?from=${from}&to=${to}&outlet_id=${outletId}`,
      ),
    enabled: Boolean(outletId),
  })
}

/** FR-RPT-008: food cost plus labour against net sales; labour typed in per month. */
export function PrimeCostTab(props: Props) {
  const { t, i18n } = useTranslation()
  const prime = usePrime(props)
  const money = (v: number) => formatMoney(v, props.currency, intlLocale(i18n.language))
  const pct = (v?: string | null) => (v == null ? '–' : `${v} %`)
  const d = prime.data
  return (
    <div className="flex flex-col gap-3">
      {prime.error && <Alert>{errorMessage(prime.error, t)}</Alert>}
      {d && (
        <Card className="grid gap-3 sm:grid-cols-2">
          <Figure label={t('prime.netSales')} value={money(d.net_sales)} />
          <Figure
            label={t('prime.prime')}
            value={`${money(d.prime_cost)} · ${pct(d.prime_cost_pct)}`}
            strong
          />
          <Figure
            label={t('prime.food')}
            value={`${money(d.food_cost)} · ${pct(d.food_cost_pct)}`}
          />
          <Figure label={t('prime.labor')} value={`${money(d.labor)} · ${pct(d.labor_pct)}`} />
        </Card>
      )}
      {d && d.labor_months_missing.length > 0 && (
        <p className="text-sm text-danger">
          {t('prime.missing', {
            months: d.labor_months_missing.map((m) => m.slice(0, 7)).join(', '),
          })}
        </p>
      )}
      {props.canEnter && <LaborForm {...props} />}
    </div>
  )
}

function Figure({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div>
      <p className="text-sm text-ink-soft">{label}</p>
      <p className={strong ? 'font-display text-2xl font-extrabold' : 'text-lg font-bold'}>
        {value}
      </p>
    </div>
  )
}

function LaborForm({ outletId, currency }: Props) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [month, setMonth] = useState(todayIso().slice(0, 7))
  const [amount, setAmount] = useState('')
  const save = useMutation({
    mutationFn: () =>
      request<void>('PUT', '/api/v1/finance/labor', {
        outlet_id: outletId,
        month: `${month}-01`,
        amount: parseMoney(amount, currency) ?? 0,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['prime'] }),
  })
  const ok = /^\d{4}-\d{2}$/.test(month) && parseMoney(amount, currency) !== null
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-bold">{t('prime.enter')}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput
          label={t('prime.month')}
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
        />
        <TextInput
          label={t('prime.amount', { currency })}
          inputMode="numeric"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
      </div>
      <p className="text-sm text-muted">{t('prime.help')}</p>
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      {save.isSuccess && <p className="text-sm text-good">{t('prime.saved')}</p>}
      <Button className="self-start" disabled={!ok || save.isPending} onClick={() => save.mutate()}>
        {t('prime.save')}
      </Button>
    </Card>
  )
}
