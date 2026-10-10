import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { formatMoney, formatNumber, intlLocale } from '../../lib/format'
import { todayIso } from '../catalog/labels'
import { useValuation } from './api'

/** FR-INV-014: stock value on any past date, rebuilt from the ledger. */
export function ValuationTab({ outletId, currency }: { outletId: string; currency: string }) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const [on, setOn] = useState(todayIso)
  const valuation = useValuation(outletId, on, i18n.language)
  const rows = valuation.data?.items ?? []
  const total = rows.reduce((sum, r) => sum + r.value, 0)

  return (
    <div className="flex flex-col gap-3">
      <TextInput
        label={t('inventory.valuationDate')}
        type="date"
        value={on}
        className="max-w-xs"
        onChange={(e) => setOn(e.target.value)}
      />
      {valuation.error && <Alert>{errorMessage(valuation.error, t)}</Alert>}
      <ul className="flex flex-col gap-1">
        {rows.map((r) => (
          <li
            key={r.item_id}
            className="flex flex-wrap justify-between gap-2 border-b border-line py-1.5"
          >
            <span>{r.name}</span>
            <span className="tabular-nums text-ink-soft">
              {`${formatNumber(Number(r.qty), locale)} ${r.unit_code} · ${formatMoney(r.value, currency, locale)}`}
            </span>
          </li>
        ))}
      </ul>
      {valuation.isSuccess && (
        <p className="font-bold">
          {t('inventory.total', { value: formatMoney(total, currency, locale) })}
        </p>
      )}
    </div>
  )
}
