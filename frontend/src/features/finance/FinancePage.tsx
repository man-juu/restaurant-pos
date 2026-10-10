import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, Tabs, TextInput } from '../../components/form'
import type { Capabilities } from '../../lib/api/types'
import { useOutlets } from '../../lib/session'
import { useSettings } from '../settings/api'
import { todayIso } from '../catalog/labels'
import { AccountsTab } from './AccountsTab'
import { BudgetTab } from './budget/BudgetTab'
import { BooksTab } from './books/BooksTab'
import { ExpensesTab } from './ExpensesTab'
import { PrimeCostTab } from './PrimeCostTab'
import { ProfitLoss } from './ProfitLoss'
import { ReceivablesTab } from './receivables/ReceivablesTab'
import { SettlementsTab } from './settlements/SettlementsTab'

const TABS = [
  'pl',
  'budget',
  'prime',
  'expenses',
  'accounts',
  'receivables',
  'platforms',
  'books',
] as const
type Tab = (typeof TABS)[number]
/** Simple mode (the default) keeps only what needs no accounting knowledge. */
const SIMPLE: readonly Tab[] = ['pl', 'budget', 'expenses', 'accounts']

const monthStart = () => `${todayIso().slice(0, 8)}01`

/** FR-FIN-001 to 007, 009: profit and loss, expenses, money accounts, receivables, books. */
export function FinancePage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const can = (code: string) => Boolean(caps?.permissions.includes(code))
  const currency = caps?.currency ?? 'IDR'
  const outlets = (useOutlets('finance').data ?? []).filter((o) => o.is_active)
  const [outletPick, setOutlet] = useState('')
  const outletId = outletPick || outlets[0]?.id || ''
  const [from, setFrom] = useState(monthStart)
  const [to, setTo] = useState(todayIso)
  const [tab, setTab] = useState<Tab>('pl')
  const tabs = useFinanceTabs()
  const shown = tabs.includes(tab) ? tab : 'pl'
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
      <Tabs tabs={tabs} value={shown} onChange={setTab} label={(k) => t(`finance.tabs.${k}`)} />
      <div role="tabpanel">
        <Panel tab={shown} ctx={{ outletId, from, to, currency, can }} />
      </div>
    </div>
  )
}

function useFinanceTabs(): readonly Tab[] {
  return useSettings().data?.finance?.mode === 'advanced' ? TABS : SIMPLE
}

type Ctx = {
  outletId: string
  from: string
  to: string
  currency: string
  can: (code: string) => boolean
}

/** One entry per tab: a lookup table instead of a chain of conditions. */
const PANELS: Record<Tab, (c: Ctx) => ReactNode> = {
  pl: (c) => <ProfitLoss outletId={c.outletId} from={c.from} to={c.to} currency={c.currency} />,
  budget: (c) => (
    <BudgetTab
      outletId={c.outletId}
      from={c.from}
      to={c.to}
      currency={c.currency}
      canManage={c.can('finance.budget.manage')}
    />
  ),
  prime: (c) => (
    <PrimeCostTab
      outletId={c.outletId}
      from={c.from}
      to={c.to}
      currency={c.currency}
      canEnter={c.can('finance.expense.create')}
    />
  ),
  expenses: (c) => (
    <ExpensesTab
      outletId={c.outletId}
      from={c.from}
      to={c.to}
      currency={c.currency}
      canCreate={c.can('finance.expense.create')}
    />
  ),
  accounts: (c) => (
    <AccountsTab
      currency={c.currency}
      canManage={c.can('finance.account.manage')}
      canMove={c.can('finance.expense.create')}
    />
  ),
  receivables: (c) => (
    <ReceivablesTab
      outletId={c.outletId}
      currency={c.currency}
      can={{
        view: c.can('sales.invoice.view'),
        manage: c.can('sales.invoice.manage'),
        payables: c.can('purchasing.bill.view'),
      }}
    />
  ),
  platforms: (c) => (
    <SettlementsTab
      outletId={c.outletId}
      from={c.from}
      to={c.to}
      currency={c.currency}
      canManage={c.can('finance.settlement.manage')}
    />
  ),
  books: (c) => (
    <BooksTab
      from={c.from}
      to={c.to}
      currency={c.currency}
      can={{
        setup: c.can('finance.ledger.setup'),
        post: c.can('finance.journal.create'),
        close: c.can('finance.period.close'),
      }}
    />
  ),
}

function Panel({ tab, ctx }: { tab: Tab; ctx: Ctx }) {
  return PANELS[tab](ctx)
}
