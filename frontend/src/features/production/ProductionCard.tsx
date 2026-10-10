import { useTranslation } from 'react-i18next'

import { Alert, Button, Card, StateBadge } from '../../components/ui'
import type { ProductionOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { useProductionAction } from './api'
import { CompleteForm } from './CompleteForm'
import { LabelLink, SheetLink } from './LabelLink'

/** One production order: plan, result (yield and cost) and the next step. */
export function ProductionCard({
  order,
  currency,
  can,
}: {
  order: ProductionOut
  currency: string
  can: { manage: boolean; reverse: boolean }
}) {
  const { t, i18n } = useTranslation()
  const step = useProductionAction()
  const done = order.status === 'completed'
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-bold">
          {order.number} · {order.item_name}
        </p>
        <StateBadge state={order.status} label={t(`production.status.${order.status}`)} />
      </div>
      <p className="text-sm text-ink-soft">
        {t('production.planned', { qty: Number(order.planned_qty), unit: order.unit_code })}
      </p>
      {done && <Result order={order} currency={currency} locale={intlLocale(i18n.language)} />}
      <SheetLink orderId={order.id} status={order.status} />
      {done && <LabelLink orderId={order.id} />}
      {step.error ? <Alert>{errorMessage(step.error, t)}</Alert> : null}
      {can.manage && order.status === 'planned' && <CompleteForm order={order} />}
      {can.manage && order.status === 'planned' && (
        <Button
          variant="ghost"
          className="self-start"
          onClick={() => step.mutate({ id: order.id, action: 'cancel' })}
        >
          {t('production.cancel')}
        </Button>
      )}
      {can.reverse && done && (
        <Button
          variant="ghost"
          className="self-start"
          onClick={() => step.mutate({ id: order.id, action: 'reverse' })}
        >
          {t('production.reverse')}
        </Button>
      )}
    </Card>
  )
}

function Result({
  order,
  currency,
  locale,
}: {
  order: ProductionOut
  currency: string
  locale: string
}) {
  const { t } = useTranslation()
  return (
    <ul className="text-sm">
      <li>{t('production.made', { qty: Number(order.actual_qty), unit: order.unit_code })}</li>
      <li>
        {t('production.variance', { qty: Number(order.yield_variance), unit: order.unit_code })}
      </li>
      {order.input_value != null && (
        <li>{t('production.cost', { value: formatMoney(order.input_value, currency, locale) })}</li>
      )}
      {order.expiry_date && <li>{t('production.useBy', { date: order.expiry_date })}</li>}
    </ul>
  )
}
