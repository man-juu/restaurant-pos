import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card, StateBadge } from '../../components/ui'
import type { OrderOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { todayIso } from '../catalog/labels'
import { pdfUrl, useOrderAction, useReceiveOrder } from './orderApi'

const QTY = /^\d{1,14}([.,]\d{1,4})?$/

/** One order: its steps (submit, approve, cancel), PDF, and receiving what arrived. */
export function OrderDetail({
  order,
  currency,
  can,
  onClose,
}: {
  order: OrderOut
  currency: string
  can: { create: boolean; approve: boolean; receive: boolean }
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const step = useOrderAction()
  const open = order.status === 'approved' || order.status === 'partially_received'
  return (
    <Card className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-xl font-bold">
          {order.number ?? t('purchasing.orders.draft')}
        </h2>
        <StateBadge state={order.status} label={t(`purchasing.orders.status.${order.status}`)} />
      </div>
      <p className="font-semibold">
        {formatMoney(order.total, currency, intlLocale(i18n.language))}
      </p>
      {step.error ? <Alert>{errorMessage(step.error, t)}</Alert> : null}
      <OrderActions order={order} can={can} step={step} onClose={onClose} />
      {can.receive && open && <ReceiveForm order={order} />}
    </Card>
  )
}

type Step = ReturnType<typeof useOrderAction>

/** The next steps this person may take on the order. */
function OrderActions({
  order,
  can,
  step,
  onClose,
}: {
  order: OrderOut
  can: { create: boolean; approve: boolean }
  step: Step
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  return (
    <div className="flex flex-wrap gap-2">
      {can.create && order.status === 'draft' && (
        <Button onClick={() => step.mutate({ id: order.id, action: 'submit' })}>
          {t('purchasing.orders.submit')}
        </Button>
      )}
      {can.approve && order.status === 'submitted' && (
        <>
          <Button
            onClick={() => step.mutate({ id: order.id, action: 'decide', body: { approve: true } })}
          >
            {t('purchasing.orders.approve')}
          </Button>
          <Button
            variant="ghost"
            onClick={() =>
              step.mutate({ id: order.id, action: 'decide', body: { approve: false } })
            }
          >
            {t('purchasing.orders.reject')}
          </Button>
        </>
      )}
      {can.create && ['draft', 'submitted', 'approved'].includes(order.status) && (
        <Button variant="ghost" onClick={() => step.mutate({ id: order.id, action: 'cancel' })}>
          {t('purchasing.orders.cancel')}
        </Button>
      )}
      {order.number && (
        <a
          className="self-center text-sm font-semibold text-accent underline"
          href={pdfUrl(order.id, i18n.language)}
        >
          {t('purchasing.orders.pdf')}
        </a>
      )}
      <Button variant="ghost" onClick={onClose}>
        {t('catalog.back')}
      </Button>
    </div>
  )
}

/** FR-PUR-005: what actually arrived (may be less than ordered, at a different price). */
function ReceiveForm({ order }: { order: OrderOut }) {
  const { t } = useTranslation()
  const receive = useReceiveOrder()
  const [qty, setQty] = useState<Record<string, string>>({})
  const [key, setKey] = useState(() => crypto.randomUUID())
  const lines = order.lines
    .filter((ln) => qty[ln.id] && QTY.test(qty[ln.id]))
    .map((ln) => ({ po_line_id: ln.id, qty: qty[ln.id].replace(',', '.') }))
  return (
    <div className="flex flex-col gap-3 border-t border-line pt-3">
      <h3 className="font-bold">{t('purchasing.orders.receive')}</h3>
      {order.lines.map((ln) => (
        <TextInput
          key={ln.id}
          label={t('purchasing.orders.arrived', { left: Number(ln.qty) - Number(ln.received_qty) })}
          inputMode="decimal"
          value={qty[ln.id] ?? ''}
          onChange={(e) => setQty({ ...qty, [ln.id]: e.target.value })}
        />
      ))}
      {receive.error ? <Alert>{errorMessage(receive.error, t)}</Alert> : null}
      <Button
        disabled={lines.length === 0 || receive.isPending}
        onClick={() =>
          receive.mutate(
            { id: order.id, body: { business_date: todayIso(), lines }, key },
            { onSuccess: () => (setQty({}), setKey(crypto.randomUUID())) },
          )
        }
      >
        {t('purchasing.orders.receiveSave')}
      </Button>
    </div>
  )
}
