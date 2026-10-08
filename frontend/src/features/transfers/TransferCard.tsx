import { useTranslation } from 'react-i18next'

import { Alert, Button, Card, StateBadge } from '../../components/ui'
import type { TransferOut } from '../../lib/api/types'
import { ApiError } from '../../lib/api/client'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { todayIso } from '../catalog/labels'
import { noteUrl, useTransferStep } from './api'
import { LineForm } from './LineForm'

export interface Can {
  request: boolean
  approve: boolean
  receive: boolean
}

/** One transfer: who sends what to whom, and this outlet's next step. */
export function TransferCard({
  transfer,
  outletId,
  names,
  currency,
  can,
}: {
  transfer: TransferOut
  outletId: string
  names: Record<string, string>
  currency: string
  can: Can
}) {
  const { t, i18n } = useTranslation()
  const isSource = transfer.from_outlet_id === outletId
  const s = transfer.status
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-bold">
          {transfer.number} · {names[transfer.from_outlet_id]} → {names[transfer.to_outlet_id]}
        </p>
        <StateBadge state={s} label={t(`transfers.status.${s}`)} />
      </div>
      <ul className="text-sm text-ink-soft">
        {transfer.lines.map((ln) => (
          <li key={ln.id}>
            {ln.item_name}: {Number(ln.shipped_qty ?? ln.approved_qty ?? ln.requested_qty)}{' '}
            {ln.unit_code}
            {ln.discrepancy_reason && ` · ${t(`transfers.reasons.${ln.discrepancy_reason}`)}`}
          </li>
        ))}
      </ul>
      {transfer.shipped_value > 0 && (
        <p className="text-sm">
          {formatMoney(transfer.shipped_value, currency, intlLocale(i18n.language))}
        </p>
      )}
      {(s === 'shipped' || s === 'received') && (
        <a
          className="text-sm font-semibold text-accent underline"
          href={noteUrl(transfer.id, i18n.language)}
          target="_blank"
          rel="noreferrer"
        >
          {t('transfers.note')}
        </a>
      )}
      {isSource && can.approve && s === 'requested' && (
        <LineForm transfer={transfer} mode="approve" />
      )}
      {!isSource && can.receive && s === 'shipped' && (
        <LineForm transfer={transfer} mode="receive" />
      )}
      <Actions transfer={transfer} isSource={isSource} can={can} />
    </Card>
  )
}

function Actions({
  transfer,
  isSource,
  can,
}: {
  transfer: TransferOut
  isSource: boolean
  can: Can
}) {
  const { t } = useTranslation()
  const step = useTransferStep()
  const short = step.error instanceof ApiError && step.error.code === 'insufficient_stock'
  const ship = (confirm: boolean) =>
    step.mutate({
      id: transfer.id,
      action: 'ship',
      body: { business_date: todayIso(), confirm_negative: confirm },
    })
  const open = transfer.status === 'requested' || transfer.status === 'approved'
  return (
    <div className="flex flex-wrap gap-2">
      {step.error ? <Alert>{errorMessage(step.error, t)}</Alert> : null}
      {isSource && can.approve && transfer.status === 'approved' && (
        <Button disabled={step.isPending} onClick={() => ship(false)}>
          {t('transfers.ship')}
        </Button>
      )}
      {short && (
        <Button variant="ghost" onClick={() => ship(true)}>
          {t('transfers.shipAnyway')}
        </Button>
      )}
      {can.request && open && (
        <Button variant="ghost" onClick={() => step.mutate({ id: transfer.id, action: 'cancel' })}>
          {t('transfers.cancel')}
        </Button>
      )}
    </div>
  )
}
