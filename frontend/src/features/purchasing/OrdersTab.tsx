import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, StateBadge } from '../../components/ui'
import type { OrderOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { OrderDetail } from './OrderDetail'
import { OrderForm } from './OrderForm'
import { useOrders } from './orderApi'

/** FR-PUR-003: purchase orders for this outlet. */
export function OrdersTab({
  outletId,
  currency,
  can,
}: {
  outletId: string
  currency: string
  can: { create: boolean; approve: boolean; receive: boolean }
}) {
  const { t, i18n } = useTranslation()
  const orders = useOrders(outletId)
  const [view, setView] = useState<OrderOut | 'new'>()
  if (view === 'new')
    return <OrderForm outletId={outletId} currency={currency} onDone={() => setView(undefined)} />
  const current = view && orders.data?.find((o) => o.id === view.id)
  if (current)
    return (
      <OrderDetail
        order={current}
        currency={currency}
        can={can}
        onClose={() => setView(undefined)}
      />
    )
  return (
    <div className="flex flex-col gap-3">
      {can.create && (
        <Button className="self-start" onClick={() => setView('new')}>
          {t('purchasing.orders.new')}
        </Button>
      )}
      {orders.error && <Alert>{errorMessage(orders.error, t)}</Alert>}
      {orders.isSuccess && orders.data.length === 0 && (
        <p className="text-ink-soft">{t('purchasing.orders.empty')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {orders.data?.map((o) => (
          <li key={o.id}>
            <button
              type="button"
              onClick={() => setView(o)}
              className="flex w-full flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-card p-3 text-left"
            >
              <span className="font-bold">{o.number ?? t('purchasing.orders.draft')}</span>
              <span className="text-sm text-muted">
                {formatMoney(o.total, currency, intlLocale(i18n.language))}
              </span>
              <StateBadge state={o.status} label={t(`purchasing.orders.status.${o.status}`)} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
