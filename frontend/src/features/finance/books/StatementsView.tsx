import { useTranslation } from 'react-i18next'

import { Alert, Card } from '../../../components/ui'
import type { TrialRow } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { formatMoney, intlLocale } from '../../../lib/format'
import { useCashFlow, useSheet, useTrial } from './glApi'

/** FR-FIN-002: trial balance and balance sheet at the end date; cash flow for the period. */
export function StatementsView({
  from,
  to,
  currency,
}: {
  from: string
  to: string
  currency: string
}) {
  const { t, i18n } = useTranslation()
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const trial = useTrial(to)
  const sheet = useSheet(to)
  const flow = useCashFlow(from, to)
  const error = trial.error ?? sheet.error ?? flow.error
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {error && <Alert>{errorMessage(error, t)}</Alert>}
      <Card className="flex flex-col gap-2">
        <h3 className="font-display font-bold">{t('books.trial')}</h3>
        <Rows rows={trial.data ?? []} money={money} />
      </Card>
      <div className="flex flex-col gap-4">
        {sheet.data && (
          <Card className="flex flex-col gap-1">
            <h3 className="font-display font-bold">{t('books.sheet')}</h3>
            <Line label={t('books.assets')} value={money(sheet.data.total_assets)} />
            <Line label={t('books.earnings')} value={money(sheet.data.current_earnings)} />
            <Line
              label={t('books.liabilitiesEquity')}
              value={money(sheet.data.total_liabilities_equity)}
            />
          </Card>
        )}
        {flow.data && (
          <Card className="flex flex-col gap-1">
            <h3 className="font-display font-bold">{t('books.flow')}</h3>
            {(['opening', 'operating', 'investing', 'financing', 'closing'] as const).map((k) => (
              <Line key={k} label={t(`books.flowRows.${k}`)} value={money(flow.data[k])} />
            ))}
          </Card>
        )}
      </div>
    </div>
  )
}

function Rows({ rows, money }: { rows: TrialRow[]; money: (v: number) => string }) {
  return (
    <table className="text-sm">
      <tbody>
        {rows.map((r) => (
          <tr key={r.account_id}>
            <td className="pr-2">{`${r.code} ${r.name}`}</td>
            <td className="text-right tabular-nums">{money(r.balance)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <p className="flex justify-between gap-2 text-sm">
      <span>{label}</span>
      <b className="tabular-nums">{value}</b>
    </p>
  )
}
