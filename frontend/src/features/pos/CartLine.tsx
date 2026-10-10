import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button, StateBadge } from '../../components/ui'
import type { PosLineOut } from '../../lib/api/types'
import { DiscountDialog } from './DiscountDialog'
import { useChangeLine, useVoid } from './posApi'
import { ReasonDialog } from './ReasonDialog'
import type { TillRights } from './Till'

/** One order line: quantity while new, discount and void (with a reason) once allowed. */
export function CartLine({
  orderId,
  line,
  money,
  currency,
  can,
}: {
  orderId: string
  line: PosLineOut
  money: (v: number) => string
  currency: string
  can: TillRights
}) {
  const { t } = useTranslation()
  const [dialog, setDialog] = useState<'discount' | 'void'>()
  const voided = line.status === 'void'
  return (
    <li className={voided ? 'flex flex-col gap-1 py-2 opacity-60' : 'flex flex-col gap-1 py-2'}>
      <div className="flex items-start justify-between gap-2">
        <LineText line={line} money={money} />
        <span className="tabular-nums">{money(line.line_total)}</span>
      </div>
      {voided ? (
        <StateBadge state="read_only" label={t('pos.voided', { reason: line.void_reason ?? '' })} />
      ) : (
        <LineControls orderId={orderId} line={line} can={can} onDialog={setDialog} />
      )}
      {dialog === 'discount' && (
        <DiscountDialog
          orderId={orderId}
          lineId={line.id}
          currency={currency}
          onClose={() => setDialog(undefined)}
        />
      )}
      {dialog === 'void' && (
        <VoidLineDialog orderId={orderId} lineId={line.id} onClose={() => setDialog(undefined)} />
      )}
    </li>
  )
}

function LineText({ line, money }: { line: PosLineOut; money: (v: number) => string }) {
  const { t } = useTranslation()
  const discount = line.discount ?? 0
  return (
    <span className="min-w-0">
      <b className={line.status === 'void' ? 'line-through' : undefined}>{line.name}</b>
      {line.modifiers.length > 0 && (
        <span className="block text-sm text-ink-soft">
          {line.modifiers.map((m) => m.name).join(', ')}
        </span>
      )}
      {line.note && <span className="block text-sm text-ink-soft">{line.note}</span>}
      {discount > 0 && (
        <span className="block text-sm text-good">
          {t('pos.lineDiscount', { amount: money(discount) })}
        </span>
      )}
    </span>
  )
}

function LineControls({
  orderId,
  line,
  can,
  onDialog,
}: {
  orderId: string
  line: PosLineOut
  can: TillRights
  onDialog: (d: 'discount' | 'void') => void
}) {
  const { t, i18n } = useTranslation()
  const change = useChangeLine(orderId, i18n.language)
  const qty = Number(line.qty)
  const setQty = (next: number) =>
    change.mutate({ lineId: line.id, qty: next > 0 ? String(next) : null })
  return (
    <div className="flex flex-wrap items-center gap-2">
      {line.status === 'new' ? (
        <>
          <Button variant="ghost" aria-label={t('pos.less')} onClick={() => setQty(qty - 1)}>
            −
          </Button>
          <span className="min-w-8 text-center tabular-nums">{qty}</span>
          <Button variant="ghost" aria-label={t('pos.more')} onClick={() => setQty(qty + 1)}>
            +
          </Button>
        </>
      ) : (
        <span className="flex items-center gap-2 text-sm">
          {qty} × <StateBadge state="sent" label={t('pos.sent')} />
        </span>
      )}
      {can.discount && (
        <Button variant="ghost" onClick={() => onDialog('discount')}>
          {t('pos.discount')}
        </Button>
      )}
      {can.void && line.status === 'sent' && (
        <Button variant="ghost" onClick={() => onDialog('void')}>
          {t('pos.void')}
        </Button>
      )}
    </div>
  )
}

export function VoidLineDialog({
  orderId,
  lineId,
  onClose,
}: {
  orderId: string
  lineId?: string
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const v = useVoid(orderId, i18n.language)
  return (
    <ReasonDialog
      title={t(lineId ? 'pos.voidLine' : 'pos.voidOrder')}
      confirm={t('pos.void')}
      pending={v.isPending}
      error={v.error}
      onClose={onClose}
      onConfirm={(reason) => v.mutate({ lineId, reason }, { onSuccess: onClose })}
    />
  )
}
