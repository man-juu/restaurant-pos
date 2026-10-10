import { useTranslation } from 'react-i18next'

import { Alert, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { useProfitLoss } from './financeApi'

/** FR-FIN-001: sales, HPP and expenses for the outlet and period. */
export function ProfitLoss({
  outletId,
  from,
  to,
  currency,
}: {
  outletId: string
  from: string
  to: string
  currency: string
}) {
  const { t, i18n } = useTranslation()
  const pl = useProfitLoss(outletId, from, to)
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  if (pl.error) return <Alert>{errorMessage(pl.error, t)}</Alert>
  if (!pl.data) return null
  const d = pl.data
  const rows: [string, number, boolean][] = [
    [t('finance.pl.netSales'), d.net_sales, false],
    [t('finance.pl.service'), d.service_charge, false],
    [t('finance.pl.revenue'), d.revenue, true],
    [t('finance.pl.cost'), -d.cost_of_sales, false],
    [t('finance.pl.gross'), d.gross_profit, true],
    ...Object.entries(d.expenses).map(([name, v]): [string, number, boolean] => [name, -v, false]),
    [t('finance.pl.expenses'), -d.expenses_total, false],
    [t('finance.pl.net'), d.net_profit, true],
  ]
  return (
    <Card className="flex flex-col gap-2">
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 tabular-nums">
        {rows.map(([label, value, bold]) => (
          <div key={label} className="contents">
            <dt className={bold ? 'font-bold' : undefined}>{label}</dt>
            <dd className={bold ? 'text-right font-bold' : 'text-right'}>{money(value)}</dd>
          </div>
        ))}
      </dl>
      <p className="text-sm text-ink-soft">
        {t('finance.pl.taxNote', { amount: money(d.tax_collected) })}
      </p>
    </Card>
  )
}
