import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import type { PosOrderOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { Cart } from './Cart'
import { PayDialog } from './PayDialog'
import { RefundDialog } from './RefundDialog'
import { useOrder } from './posApi'
import type { TillProps } from './Till'

/** One order: the cart while open, the payment result once paid. */
export function OrderView({
  orderId,
  onClose,
  ...props
}: TillProps & { orderId: string; onClose: () => void }) {
  const { t, i18n } = useTranslation()
  const order = useOrder(orderId, i18n.language)
  const [paying, setPaying] = useState(false)
  if (order.error) return <Alert>{errorMessage(order.error, t)}</Alert>
  if (!order.data) return null
  if (order.data.status !== 'open')
    return <PaidCard {...props} order={order.data} onNext={onClose} />
  return (
    <>
      <Cart
        order={order.data}
        currency={props.currency}
        can={props.can}
        onPay={() => setPaying(true)}
        onClose={onClose}
      />
      {paying && (
        <PayDialog
          order={order.data}
          methods={props.methods}
          pos={props.pos}
          currency={props.currency}
          onDone={() => setPaying(false)}
          onClose={() => setPaying(false)}
        />
      )}
    </>
  )
}

function PaidCard({
  order,
  currency,
  can,
  methods,
  onNext,
}: TillProps & { order: PosOrderOut; onNext: () => void }) {
  const { t, i18n } = useTranslation()
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const payments = order.payments ?? []
  const change = payments.reduce((sum, p) => sum + p.change, 0)
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-xl font-bold">
        {t(`pos.status.${order.status}`, { number: order.number })}
      </h2>
      {change > 0 && (
        <p className="text-2xl font-extrabold tabular-nums" role="status">
          {t('pos.change', { amount: money(change) })}
        </p>
      )}
      <ul className="text-sm">
        {payments.map((p, i) => (
          <li key={i}>
            {p.method}: {money(p.amount)}
          </li>
        ))}
      </ul>
      <Button onClick={onNext}>{t('pos.nextOrder')}</Button>
      {can.refund && <RefundArea order={order} methods={methods} money={money} />}
    </Card>
  )
}

/** The refund's state, or the button to ask for one (FR-SAL-008). */
function RefundArea({
  order,
  methods,
  money,
}: {
  order: PosOrderOut
  methods: TillProps['methods']
  money: (v: number) => string
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const refund = order.refund
  const mayAsk = order.status === 'paid' && (!refund || refund.status === 'rejected')
  return (
    <>
      {refund && (
        <p className="text-sm">
          {t(`pos.refundStatus.${refund.status}`, { amount: money(refund.amount) })}
        </p>
      )}
      {mayAsk && (
        <Button variant="ghost" onClick={() => setOpen(true)}>
          {t('pos.refund')}
        </Button>
      )}
      {open && (
        <RefundDialog
          orderId={order.id}
          methods={methods}
          defaultMethod={firstMethod(order, methods)}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  )
}

const firstMethod = (order: PosOrderOut, methods: TillProps['methods']) =>
  order.payments?.[0]?.method ?? methods[0]?.code ?? 'cash'
