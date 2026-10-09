import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, TextInput } from '../../components/form'
import type { Capabilities } from '../../lib/api/types'
import { useOutlets } from '../../lib/session'
import { todayIso } from '../catalog/labels'
import { REPORTS } from './catalog'
import { ReportTable } from './ReportTable'

const monthStart = () => `${todayIso().slice(0, 8)}01`

/** FR-RPT-001 to 006, 011: reports for the outlets this person may see. */
export function ReportsPage() {
  const { t, i18n } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const allowed = REPORTS.filter((r) => caps?.permissions.includes(r.permission))
  const outlets = useOutlets()
  const [key, setKey] = useState('')
  const [from, setFrom] = useState(monthStart)
  const [to, setTo] = useState(todayIso)
  const [outletId, setOutletId] = useState('')
  const def = allowed.find((r) => r.key === key) ?? allowed[0]
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('reports.title')}</h1>
      {!def && <p className="text-ink-soft">{t('reports.none')}</p>}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SelectInput
          label={t('reports.report')}
          value={def?.key ?? ''}
          onChange={(e) => setKey(e.target.value)}
        >
          {allowed.map((r) => (
            <option key={r.key} value={r.key}>
              {t(`reports.names.${r.key}`)}
            </option>
          ))}
        </SelectInput>
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
        <SelectInput
          label={t('inventory.outlet')}
          value={outletId}
          onChange={(e) => setOutletId(e.target.value)}
        >
          <option value="">{t('reports.allOutlets')}</option>
          {outlets.data?.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </SelectInput>
      </div>
      {def && (
        <ReportTable
          def={def}
          filters={{ from, to, outletId, lang: i18n.language }}
          currency={caps?.currency ?? 'IDR'}
        />
      )}
    </div>
  )
}
