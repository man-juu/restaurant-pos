import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Alert, Card } from '../../../components/ui'
import { request } from '../../../lib/api/client'
import type { ReconcileRow } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { formatMoney, intlLocale } from '../../../lib/format'

/** Gate 3: what stock, customer invoices and vendor debts say, against their accounts. */
export function ReconcileView({ currency }: { currency: string }) {
  const { t, i18n } = useTranslation()
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const rows = useQuery({
    queryKey: ['gl', 'reconcile'],
    queryFn: () => request<ReconcileRow[]>('GET', '/api/v1/finance/gl/reconcile'),
  })
  return (
    <Card className="flex flex-col gap-3">
      <p className="text-sm text-ink-soft">{t('books.reconcile.help')}</p>
      {rows.error && <Alert>{errorMessage(rows.error, t)}</Alert>}
      <ul className="flex flex-col gap-2">
        {rows.data?.map((r) => (
          <li key={r.name} className="border-b border-line pb-2">
            <p className="font-semibold">{t(`books.reconcile.names.${r.name}`)}</p>
            <p className="text-sm text-ink-soft">
              {t('books.reconcile.line', {
                sub: money(r.subledger),
                books: money(r.books),
                code: r.account_code ?? '–',
              })}
            </p>
            <p className={r.difference ? 'text-sm font-bold text-danger' : 'text-sm text-good'}>
              {r.difference
                ? t('books.reconcile.diff', { amount: money(r.difference) })
                : t('books.reconcile.ok')}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  )
}
