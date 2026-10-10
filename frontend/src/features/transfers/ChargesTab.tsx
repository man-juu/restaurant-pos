import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { todayIso } from '../catalog/labels'
import { useCharges } from './standingApi'

/** FR-TRF-006: what outlets charged each other for shipped goods, against their cost. */
export function ChargesTab({
  names,
  currency,
}: {
  names: Record<string, string>
  currency: string
}) {
  const { t, i18n } = useTranslation()
  const [from, setFrom] = useState(`${todayIso().slice(0, 8)}01`)
  const [to, setTo] = useState(todayIso)
  const rows = useCharges(from, to)
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  return (
    <Card className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput
          label={t('reports.from')}
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <TextInput
          label={t('reports.to')}
          type="date"
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
      </div>
      <p className="text-sm text-ink-soft">{t('standing.chargesHelp')}</p>
      {rows.error && <Alert>{errorMessage(rows.error, t)}</Alert>}
      {rows.isSuccess && rows.data.length === 0 && (
        <p className="text-ink-soft">{t('standing.noCharges')}</p>
      )}
      <ul className="flex flex-col gap-1">
        {rows.data?.map((r) => (
          <li key={`${r.from_outlet_id}-${r.to_outlet_id}`} className="border-b border-line py-1">
            <span className="font-semibold">{`${names[r.from_outlet_id] ?? ''} → ${names[r.to_outlet_id] ?? ''}`}</span>
            <span className="block text-sm text-ink-soft">
              {t('standing.chargeLine', {
                count: r.transfers,
                cost: money(r.cost),
                charge: money(r.charge),
              })}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
