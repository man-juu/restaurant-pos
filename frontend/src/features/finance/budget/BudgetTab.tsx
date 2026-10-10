import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Alert, Card } from '../../../components/ui'
import { request } from '../../../lib/api/client'
import type { BudgetLine, BudgetReport } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { formatMoney, intlLocale } from '../../../lib/format'
import { BudgetForm } from './BudgetForm'

export type BudgetProps = {
  outletId: string
  from: string
  to: string
  currency: string
  canManage: boolean
}

function useBudget({ outletId, from, to }: BudgetProps) {
  return useQuery({
    queryKey: ['budget', outletId, from, to],
    queryFn: () =>
      request<BudgetReport>(
        'GET',
        `/api/v1/finance/budgets/vs-actual?from=${from}&to=${to}&outlet_id=${outletId}`,
      ),
    enabled: Boolean(outletId),
  })
}

/** FR-FIN-010: the plan per outlet and month against what happened. */
export function BudgetTab(props: BudgetProps) {
  const { t, i18n } = useTranslation()
  const report = useBudget(props)
  const money = (v: number) => formatMoney(v, props.currency, intlLocale(i18n.language))
  const d = report.data
  return (
    <div className="flex flex-col gap-3">
      {report.error && <Alert>{errorMessage(report.error, t)}</Alert>}
      {d && (
        <Card className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-ink-soft">
                <th className="py-1">{t('budget.line')}</th>
                <th className="text-right">{t('budget.plan')}</th>
                <th className="text-right">{t('budget.actual')}</th>
                <th className="text-right">{t('budget.variance')}</th>
              </tr>
            </thead>
            <tbody>
              {d.lines.map((l) => (
                <Row key={l.line} line={l} money={money} />
              ))}
            </tbody>
          </table>
        </Card>
      )}
      {d && d.months_missing.length > 0 && (
        <p className="text-sm text-danger">
          {t('budget.missing', { months: d.months_missing.map((m) => m.slice(0, 7)).join(', ') })}
        </p>
      )}
      {props.canManage && <BudgetForm {...props} />}
    </div>
  )
}

function Row({ line, money }: { line: BudgetLine; money: (v: number) => string }) {
  const { t } = useTranslation()
  const pct = line.variance_pct == null ? '' : ` (${line.variance_pct} %)`
  return (
    <tr className={line.line === 'net_profit' ? 'border-t font-bold' : ''}>
      <td className="py-1">{t(`budget.lines.${line.line}`)}</td>
      <td className="text-right">{money(line.budget)}</td>
      <td className="text-right">{money(line.actual)}</td>
      <td className={`text-right ${line.favourable ? 'text-good' : 'text-danger'}`}>
        {money(line.variance)}
        {pct}
      </td>
    </tr>
  )
}
