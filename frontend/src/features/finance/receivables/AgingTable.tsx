import { useTranslation } from 'react-i18next'

import { Card } from '../../../components/ui'
import type { AgingRow } from '../../../lib/api/types'
import { formatMoney, intlLocale } from '../../../lib/format'

const BUCKETS = ['current', 'days_1_30', 'days_31_60', 'days_61_90', 'over_90'] as const

/** FR-FIN-006: open balances per customer or vendor by how long they are past due. */
export function AgingTable({
  title,
  rows,
  currency,
}: {
  title: string
  rows: AgingRow[]
  currency: string
}) {
  const { t, i18n } = useTranslation()
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  return (
    <Card>
      <h2 className="mb-2 font-bold">{title}</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{t('ar.aging.none')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted">
                <th className="py-1 pr-2">{t('ar.aging.party')}</th>
                {BUCKETS.map((b) => (
                  <th key={b} className="py-1 pr-2 text-right">
                    {t(`ar.aging.${b}`)}
                  </th>
                ))}
                <th className="py-1 text-right">{t('ar.aging.total')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.party_id} className="border-t border-line">
                  <td className="py-1 pr-2">{r.party_name}</td>
                  {BUCKETS.map((b) => (
                    <td key={b} className={`py-1 pr-2 text-right ${cell(b, r[b])}`}>
                      {money(r[b])}
                    </td>
                  ))}
                  <td className="py-1 text-right font-bold">{money(r.total)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

const cell = (bucket: string, value: number) =>
  bucket !== 'current' && value > 0 ? 'text-danger' : ''
