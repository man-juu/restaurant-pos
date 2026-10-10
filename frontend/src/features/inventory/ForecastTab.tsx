import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Alert, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { ForecastRow } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatNumber, intlLocale } from '../../lib/format'

const DAYS = 7

/** FR-INV-018: what each item should need over the next week, from weekday averages with
 * trend, and the economic order quantity when the tenant set an order cost. */
export function ForecastTab({ outletId }: { outletId: string }) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const rows = useQuery({
    queryKey: ['forecast', outletId, i18n.language],
    queryFn: () =>
      request<ForecastRow[]>(
        'GET',
        `/api/v1/inventory/forecast?outlet_id=${outletId}&days=${DAYS}&lang=${i18n.language.slice(0, 2)}`,
      ),
  })
  const f = (v: string | number | null | undefined) => formatNumber(Number(v ?? 0), locale)
  return (
    <Card className="flex flex-col gap-2">
      <p className="text-sm text-ink-soft">{t('planning.forecastHelp', { days: DAYS })}</p>
      {rows.error && <Alert>{errorMessage(rows.error, t)}</Alert>}
      {rows.isSuccess && rows.data.length === 0 && (
        <p className="text-ink-soft">{t('planning.forecastEmpty')}</p>
      )}
      <ul className="flex flex-col gap-1">
        {rows.data?.map((r) => {
          const week = r.days.reduce((s, d) => s + Number(d), 0)
          return (
            <li key={r.item_id} className="flex flex-col border-b border-line py-1.5">
              <span className="font-semibold">{r.name}</span>
              <span className="text-sm text-ink-soft">
                {t('planning.forecastLine', {
                  week: f(week),
                  daily: f(r.daily),
                  have: f(r.on_hand),
                  unit: r.unit_code,
                })}
                {' · '}
                {r.enough_history
                  ? t('planning.trend', { pct: f((Number(r.trend) - 1) * 100) })
                  : t('planning.shortHistory')}
                {r.eoq && ` · ${t('planning.eoq', { qty: f(r.eoq), unit: r.unit_code })}`}
              </span>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
