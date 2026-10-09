import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { useDecideRefund, usePendingRefunds } from './posApi'

/** docs/03 section 7: refunds waiting for a manager. Your own requests cannot be approved
 * by you (the server refuses); they are listed so you can see they are waiting. */
export function RefundApprovals({
  outletId,
  currency,
  userId,
}: {
  outletId: string
  currency: string
  userId?: string
}) {
  const { t, i18n } = useTranslation()
  const pending = usePendingRefunds(outletId, true)
  const decide = useDecideRefund()
  if (!pending.data?.length) return null
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  return (
    <Card className="flex flex-col gap-2">
      <h2 className="font-display text-lg font-bold">{t('pos.refundsWaiting')}</h2>
      {decide.error ? <Alert>{errorMessage(decide.error, t)}</Alert> : null}
      <ul className="flex flex-col gap-2">
        {pending.data.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-2">
            <span>
              <b>{money(r.amount)}</b> · {r.reason}
            </span>
            {r.created_by !== userId && (
              <span className="flex gap-2">
                <Button onClick={() => decide.mutate({ id: r.id, decision: 'approve' })}>
                  {t('pos.approve')}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => decide.mutate({ id: r.id, decision: 'reject' })}
                >
                  {t('pos.reject')}
                </Button>
              </span>
            )}
          </li>
        ))}
      </ul>
    </Card>
  )
}
