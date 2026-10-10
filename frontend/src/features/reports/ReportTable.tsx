import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Alert, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { Report } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { type Filters, type ReportDef, reportUrl } from './catalog'

const MONEY_COLS = new Set([
  'net_sales',
  'discount',
  'total',
  'food_cost',
  'margin',
  'value',
  'net_value',
  'variance_value',
  'unit_margin',
  'total_margin',
])

function Cell({
  col,
  value,
  currency,
  weekday,
}: {
  col: string
  value: unknown
  currency: string
  weekday: boolean
}) {
  const { t, i18n } = useTranslation()
  if (value == null || value === '') return <>–</>
  if (MONEY_COLS.has(col) && typeof value === 'number')
    return <>{formatMoney(value, currency, intlLocale(i18n.language))}</>
  if (col.endsWith('_pct')) return <>{`${String(value)} %`}</>
  if (weekday && col === 'name') return <>{t(`reports.weekdays.${String(value)}`)}</>
  if (col === 'class') return <>{t(`reports.menuClass.${String(value)}`)}</>
  return <>{String(value)}</>
}

/** FR-RPT-006, 010: one report as a table, with when it was computed and downloads. */
export function ReportTable({
  def,
  filters,
  currency,
}: {
  def: ReportDef
  filters: Filters
  currency: string
}) {
  const { t, i18n } = useTranslation()
  const report = useQuery({
    queryKey: ['report', def.key, filters],
    queryFn: () => request<Report>('GET', reportUrl(def, filters)),
  })
  const data = report.data
  const weekday = def.params?.by === 'weekday'
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {data && (
          <p className="text-sm text-ink-soft">
            {t('reports.computed', {
              at: new Date(data.computed_at).toLocaleString(i18n.language),
            })}
          </p>
        )}
        <span className="flex gap-3 text-sm font-semibold">
          <a className="text-accent underline" href={reportUrl(def, filters, 'csv')}>
            {t('reports.csv')}
          </a>
          <a className="text-accent underline" href={reportUrl(def, filters, 'xlsx')}>
            {t('reports.excel')}
          </a>
        </span>
      </div>
      {report.error && <Alert>{errorMessage(report.error, t)}</Alert>}
      {data && data.rows.length === 0 && <p className="text-ink-soft">{t('reports.empty')}</p>}
      {data && data.rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr>
                {data.columns.map((c) => (
                  <th key={c} className="border-b border-line p-2 text-left">
                    {t(`reports.cols.${c}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row, i) => (
                <tr key={i} className="border-b border-line">
                  {data.columns.map((c) => (
                    <td key={c} className="p-2 tabular-nums">
                      <Cell col={c} value={row[c]} currency={currency} weekday={weekday} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data?.totals && <Totals totals={data.totals} currency={currency} />}
    </Card>
  )
}

function Totals({ totals, currency }: { totals: Record<string, unknown>; currency: string }) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const money = (v: unknown) => (typeof v === 'number' ? formatMoney(v, currency, locale) : '–')
  const best = Array.isArray(totals.best_days)
    ? (totals.best_days as { date: string; net_sales: number }[])
    : []
  return (
    <div className="flex flex-col gap-1 text-sm">
      {'net_sales' in totals && (
        <p>
          {t('reports.netTotal', { value: money(totals.net_sales) })}
          {'previous_net_sales' in totals &&
            ` · ${t('reports.previous', { value: money(totals.previous_net_sales), change: totals.change_pct ?? '–' })}`}
        </p>
      )}
      {'total' in totals && <p>{t('reports.grandTotal', { value: money(totals.total) })}</p>}
      {'value' in totals && <p>{t('reports.grandTotal', { value: money(totals.value) })}</p>}
      {'average_unit_margin' in totals && (
        <p>
          {t('reports.menuBars', {
            margin: money(totals.average_unit_margin),
            mix: totals.popularity_bar_pct,
          })}
        </p>
      )}
      {best.length > 0 && (
        <p>
          {t('reports.bestDays', {
            days: best.map((b) => `${b.date} (${money(b.net_sales)})`).join(', '),
          })}
        </p>
      )}
    </div>
  )
}
