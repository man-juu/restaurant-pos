import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import type { PosOrderOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { Cart } from './Cart'
import { PayDialog } from './PayDialog'
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
    return <PaidCard order={order.data} currency={props.currency} onNext={onClose} />
  return (
    <>
      <Cart
        order={order.data}
        currency={props.currency}
        canPay={props.canPay}
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
  onNext,
}: {
  order: PosOrderOut
  currency: string
  onNext: () => void
}) {
  const { t, i18n } = useTranslation()
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const change = (order.payments ?? []).reduce((sum, p) => sum + p.change, 0)
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
        {(order.payments ?? []).map((p, i) => (
          <li key={i}>
            {p.method}: {money(p.amount)}
          </li>
        ))}
      </ul>
      <Button onClick={onNext}>{t('pos.nextOrder')}</Button>
    </Card>
  )
}
