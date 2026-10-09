import { useTranslation } from 'react-i18next'

import { Alert, Button, Card, StateBadge } from '../../components/ui'
import type { PosLineOut, PosOrderOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { useChangeLine, useOrderStep } from './posApi'

/** The order being served: lines, totals and the next steps (FR-SAL-005). */
export function Cart({
  order,
  currency,
  canPay,
  onPay,
  onClose,
}: {
  order: PosOrderOut
  currency: string
  canPay: boolean
  onPay: () => void
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const step = useOrderStep(order.id, i18n.language)
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const unsent = order.lines.some((l) => l.status === 'new')
  const anySent = order.lines.some((l) => l.status === 'sent')
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-xl font-bold">{order.label ?? order.number}</h2>
        <span className="text-sm text-ink-soft">{order.number}</span>
      </div>
      {order.lines.length === 0 && <p className="text-ink-soft">{t('pos.emptyOrder')}</p>}
      <ul className="flex flex-col divide-y divide-line">
        {order.lines.map((line) => (
          <CartLine key={line.id} orderId={order.id} line={line} money={money} />
        ))}
      </ul>
      <dl className="grid grid-cols-[1fr_auto] gap-x-3 text-sm tabular-nums">
        <dt>{t('pos.subtotal')}</dt>
        <dd className="text-right">{money(order.totals.subtotal)}</dd>
        {order.totals.service_charge > 0 && (
          <>
            <dt>{t('pos.serviceCharge')}</dt>
            <dd className="text-right">{money(order.totals.service_charge)}</dd>
          </>
        )}
        <dt>{t('pos.tax')}</dt>
        <dd className="text-right">{money(order.totals.tax)}</dd>
        <dt className="text-base font-bold">{t('pos.total')}</dt>
        <dd className="text-right text-base font-bold">{money(order.totals.total)}</dd>
      </dl>
      {step.error ? <Alert>{errorMessage(step.error, t)}</Alert> : null}
      <div className="grid grid-cols-2 gap-2">
        <Button disabled={!unsent || step.isPending} onClick={() => step.mutate('send')}>
          {t('pos.send')}
        </Button>
        {canPay && (
          <Button disabled={order.lines.length === 0} onClick={onPay}>
            {t('pos.pay')}
          </Button>
        )}
        {!anySent && (
          <Button variant="ghost" onClick={() => step.mutate('cancel', { onSuccess: onClose })}>
            {t('pos.cancelOrder')}
          </Button>
        )}
        <Button variant="ghost" onClick={onClose}>
          {t('pos.otherOrders')}
        </Button>
      </div>
    </Card>
  )
}

function CartLine({
  orderId,
  line,
  money,
}: {
  orderId: string
  line: PosLineOut
  money: (v: number) => string
}) {
  const { t, i18n } = useTranslation()
  const change = useChangeLine(orderId, i18n.language)
  const qty = Number(line.qty)
  const setQty = (next: number) =>
    change.mutate({ lineId: line.id, qty: next > 0 ? String(next) : null })
  return (
    <li className="flex flex-col gap-1 py-2">
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0">
          <b>{line.name}</b>
          {line.modifiers.length > 0 && (
            <span className="block text-sm text-ink-soft">
              {line.modifiers.map((m) => m.name).join(', ')}
            </span>
          )}
          {line.note && <span className="block text-sm text-ink-soft">{line.note}</span>}
        </span>
        <span className="tabular-nums">{money(line.line_total)}</span>
      </div>
      {line.status === 'new' ? (
        <div className="flex items-center gap-2">
          <Button variant="ghost" aria-label={t('pos.less')} onClick={() => setQty(qty - 1)}>
            −
          </Button>
          <span className="min-w-8 text-center tabular-nums">{qty}</span>
          <Button variant="ghost" aria-label={t('pos.more')} onClick={() => setQty(qty + 1)}>
            +
          </Button>
        </div>
      ) : (
        <span className="flex items-center gap-2 text-sm">
          {qty} × <StateBadge state="sent" label={t('pos.sent')} />
        </span>
      )}
    </li>
  )
}
