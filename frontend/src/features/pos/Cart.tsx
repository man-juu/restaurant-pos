import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import type { PosOrderOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { CartLine, VoidLineDialog } from './CartLine'
import { DiscountDialog } from './DiscountDialog'
import { PrintButtons } from './PrintButtons'
import { useOrderStep } from './posApi'
import type { TillRights } from './Till'

/** The order being served: lines, totals and the next steps (FR-SAL-005, 007, 008). */
export function Cart({
  order,
  currency,
  can,
  onPay,
  onClose,
}: {
  order: PosOrderOut
  currency: string
  can: TillRights
  onPay: () => void
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-xl font-bold">{order.label ?? order.number}</h2>
        <span className="text-sm text-ink-soft">{order.number}</span>
      </div>
      {order.lines.length === 0 && <p className="text-ink-soft">{t('pos.emptyOrder')}</p>}
      <ul className="flex flex-col divide-y divide-line">
        {order.lines.map((line) => (
          <CartLine
            key={line.id}
            orderId={order.id}
            line={line}
            money={money}
            currency={currency}
            can={can}
          />
        ))}
      </ul>
      <Totals order={order} money={money} />
      {order.lines.length > 0 && <PrintButtons orderId={order.id} currency={currency} />}
      <CartActions order={order} currency={currency} can={can} onPay={onPay} onClose={onClose} />
    </Card>
  )
}

function Totals({ order, money }: { order: PosOrderOut; money: (v: number) => string }) {
  const { t } = useTranslation()
  const rows: [string, number][] = [
    [t('pos.subtotal'), order.totals.subtotal],
    [t('pos.discount'), -(order.totals.discount ?? 0)],
    [t('pos.serviceCharge'), order.totals.service_charge],
    [t('pos.tax'), order.totals.tax],
  ]
  return (
    <dl className="grid grid-cols-[1fr_auto] gap-x-3 text-sm tabular-nums">
      {rows
        .filter(([, v], i) => i === 0 || v !== 0)
        .map(([label, v]) => (
          <div key={label} className="contents">
            <dt>{label}</dt>
            <dd className="text-right">{money(v)}</dd>
          </div>
        ))}
      <dt className="text-base font-bold">{t('pos.total')}</dt>
      <dd className="text-right text-base font-bold">{money(order.totals.total)}</dd>
    </dl>
  )
}

function CartActions({
  order,
  currency,
  can,
  onPay,
  onClose,
}: {
  order: PosOrderOut
  currency: string
  can: TillRights
  onPay: () => void
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const step = useOrderStep(order.id, i18n.language)
  const [dialog, setDialog] = useState<'discount' | 'void'>()
  const live = order.lines.filter((l) => l.status !== 'void')
  const close = () => setDialog(undefined)
  return (
    <>
      {step.error ? <Alert>{errorMessage(step.error, t)}</Alert> : null}
      <div className="grid grid-cols-2 gap-2">
        <Button
          disabled={!live.some((l) => l.status === 'new') || step.isPending}
          onClick={() => step.mutate('send')}
        >
          {t('pos.send')}
        </Button>
        {can.pay && (
          <Button disabled={live.length === 0} onClick={onPay}>
            {t('pos.pay')}
          </Button>
        )}
        <MoreActions
          live={live}
          can={can}
          onDialog={setDialog}
          onCancel={() => step.mutate('cancel', { onSuccess: onClose })}
        />
        <Button variant="ghost" onClick={onClose}>
          {t('pos.otherOrders')}
        </Button>
      </div>
      {dialog === 'discount' && (
        <DiscountDialog orderId={order.id} currency={currency} onClose={close} />
      )}
      {dialog === 'void' && <VoidLineDialog orderId={order.id} onClose={close} />}
    </>
  )
}

/** Discount the order; void it once something was sent, else simply cancel it. */
function MoreActions({
  live,
  can,
  onDialog,
  onCancel,
}: {
  live: PosOrderOut['lines']
  can: TillRights
  onDialog: (d: 'discount' | 'void') => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const anySent = live.some((l) => l.status === 'sent')
  return (
    <>
      {can.discount && live.length > 0 && (
        <Button variant="ghost" onClick={() => onDialog('discount')}>
          {t('pos.discountOrder')}
        </Button>
      )}
      {anySent && can.void && (
        <Button variant="ghost" onClick={() => onDialog('void')}>
          {t('pos.voidOrder')}
        </Button>
      )}
      {!anySent && (
        <Button variant="ghost" onClick={onCancel}>
          {t('pos.cancelOrder')}
        </Button>
      )}
    </>
  )
}
