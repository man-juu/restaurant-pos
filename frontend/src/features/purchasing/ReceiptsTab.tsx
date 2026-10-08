import { useTranslation } from 'react-i18next'

import { Alert, Button, StateBadge } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { formatDate, formatMoney, intlLocale } from '../../lib/format'
import { useReceipts, useReverseReceipt } from './api'

/** Goods received at this outlet; a mistake is undone by a reversal (FR-X-005). */
export function ReceiptsTab({
  outletId,
  currency,
  canReverse,
}: {
  outletId: string
  currency: string
  canReverse: boolean
}) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const receipts = useReceipts(outletId)
  const reverse = useReverseReceipt()
  return (
    <div className="flex flex-col gap-3">
      {receipts.error && <Alert>{errorMessage(receipts.error, t)}</Alert>}
      {reverse.error ? <Alert>{errorMessage(reverse.error, t)}</Alert> : null}
      {receipts.isSuccess && receipts.data.length === 0 && (
        <p className="text-ink-soft">{t('purchasing.receipts.empty')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {receipts.data?.map((r) => (
          <li
            key={r.id}
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line bg-card p-3"
          >
            <div>
              <p className="font-bold">
                {r.number} · {r.vendor_name ?? t('purchasing.receipts.vendor')}
              </p>
              <p className="text-sm text-muted">
                {formatDate(r.business_date, locale)} · {formatMoney(r.total, currency, locale)}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <StateBadge state={r.status} label={t(`purchasing.receipts.${r.status}`)} />
              {canReverse && r.status === 'posted' && (
                <Button
                  variant="ghost"
                  onClick={() => reverse.mutate(r.id)}
                  disabled={reverse.isPending}
                >
                  {t('purchasing.receipts.reverse')}
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
