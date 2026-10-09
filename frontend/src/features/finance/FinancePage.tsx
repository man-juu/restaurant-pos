import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, Tabs, TextInput } from '../../components/form'
import type { Capabilities } from '../../lib/api/types'
import { useOutlets } from '../../lib/session'
import { todayIso } from '../catalog/labels'
import { AccountsTab } from './AccountsTab'
import { ExpensesTab } from './ExpensesTab'
import { ProfitLoss } from './ProfitLoss'

const TABS = ['pl', 'expenses', 'accounts'] as const
type Tab = (typeof TABS)[number]

const monthStart = () => `${todayIso().slice(0, 8)}01`

/** FR-FIN-001: profit and loss, expenses and money accounts. */
export function FinancePage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const can = (code: string) => Boolean(caps?.permissions.includes(code))
  const currency = caps?.currency ?? 'IDR'
  const outlets = (useOutlets().data ?? []).filter((o) => o.is_active)
  const [outletPick, setOutlet] = useState('')
  const outletId = outletPick || outlets[0]?.id || ''
  const [from, setFrom] = useState(monthStart)
  const [to, setTo] = useState(todayIso)
  const [tab, setTab] = useState<Tab>('pl')
  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-3xl font-extrabold">{t('finance.title')}</h1>
      <div className="grid gap-3 sm:grid-cols-3">
        <SelectInput
          label={t('pos.outlet')}
          value={outletId}
          onChange={(e) => setOutlet(e.target.value)}
        >
          {outlets.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
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
      </div>
      <Tabs tabs={TABS} value={tab} onChange={setTab} label={(k) => t(`finance.tabs.${k}`)} />
      <div role="tabpanel">
        {tab === 'pl' && <ProfitLoss outletId={outletId} from={from} to={to} currency={currency} />}
        {tab === 'expenses' && (
          <ExpensesTab
            outletId={outletId}
            from={from}
            to={to}
            currency={currency}
            canCreate={can('finance.expense.create')}
          />
        )}
        {tab === 'accounts' && (
          <AccountsTab
            currency={currency}
            canManage={can('finance.account.manage')}
            canMove={can('finance.expense.create')}
          />
        )}
      </div>
    </div>
  )
}
