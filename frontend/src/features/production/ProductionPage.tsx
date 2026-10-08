import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, TextInput } from '../../components/form'
import { Alert } from '../../components/ui'
import type { Capabilities } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useOutlets } from '../../lib/session'
import { todayIso } from '../catalog/labels'
import { useProduction } from './api'
import { PlanForm } from './PlanForm'
import { ProductionCard } from './ProductionCard'

/** FR-PRD-001 to 004: plan what the kitchen makes today, then record what came out. */
export function ProductionPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const has = (code: string) => Boolean(caps?.permissions.includes(code))
  const outlets = useOutlets()
  const [picked, setPicked] = useState('')
  const [date, setDate] = useState(todayIso)
  const outletId = picked || outlets.data?.find((o) => o.is_active)?.id || ''
  const can = { manage: has('production.order.manage'), reverse: has('production.order.reverse') }
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('production.title')}</h1>
      <div className="grid max-w-xl gap-3 sm:grid-cols-2">
        <SelectInput
          label={t('inventory.outlet')}
          value={outletId}
          onChange={(e) => setPicked(e.target.value)}
        >
          {outlets.data?.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </SelectInput>
        <TextInput
          label={t('production.date')}
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </div>
      {can.manage && outletId && <PlanForm outletId={outletId} date={date} />}
      <DayList outletId={outletId} date={date} currency={caps?.currency ?? 'IDR'} can={can} />
    </div>
  )
}

function DayList({
  outletId,
  date,
  currency,
  can,
}: {
  outletId: string
  date: string
  currency: string
  can: { manage: boolean; reverse: boolean }
}) {
  const { t, i18n } = useTranslation()
  const orders = useProduction(outletId, i18n.language)
  const today = orders.data?.filter((o) => o.production_date === date) ?? []
  return (
    <>
      {orders.error && <Alert>{errorMessage(orders.error, t)}</Alert>}
      {orders.isSuccess && today.length === 0 && (
        <p className="text-ink-soft">{t('production.empty')}</p>
      )}
      {today.map((o) => (
        <ProductionCard key={o.id} order={o} currency={currency} can={can} />
      ))}
    </>
  )
}
