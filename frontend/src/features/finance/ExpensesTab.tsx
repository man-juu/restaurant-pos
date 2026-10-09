import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card, StateBadge } from '../../components/ui'
import type { ExpenseOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { parseMoney } from '../../lib/money'
import { todayIso } from '../catalog/labels'
import {
  post,
  useAccounts,
  useExpenseCategories,
  useExpenses,
  useFinanceChange,
} from './financeApi'

/** FR-FIN-001: what was spent, by category and from which account; reversed, never deleted. */
export function ExpensesTab(props: {
  outletId: string
  from: string
  to: string
  currency: string
  canCreate: boolean
}) {
  const { t, i18n } = useTranslation()
  const list = useExpenses(props.outletId, props.from, props.to)
  const reverse = useFinanceChange((id: string) =>
    post<ExpenseOut>(`/expenses/${id}/reverse`, undefined),
  )
  const money = (v: number) => formatMoney(v, props.currency, intlLocale(i18n.language))
  return (
    <div className="flex flex-col gap-4">
      {props.canCreate && <ExpenseForm outletId={props.outletId} currency={props.currency} />}
      {list.error || reverse.error ? (
        <Alert>{errorMessage(list.error ?? reverse.error, t)}</Alert>
      ) : null}
      <ul className="flex flex-col gap-2">
        {list.data?.map((e) => (
          <li
            key={e.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line px-3 py-2"
          >
            <span>
              <b>{money(e.amount)}</b> · {e.spent_on} · {e.payee ?? e.number}
            </span>
            {e.status === 'reversed' ? (
              <StateBadge state="reversed" label={t('finance.reversed')} />
            ) : (
              props.canCreate && (
                <Button variant="ghost" onClick={() => reverse.mutate(e.id)}>
                  {t('finance.reverse')}
                </Button>
              )
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

function ExpenseForm({ outletId, currency }: { outletId: string; currency: string }) {
  const { t } = useTranslation()
  const { accounts, categories, d, setD, account, category, ok, body } = useExpenseDraft(
    outletId,
    currency,
  )
  const [key, setKey] = useState(() => crypto.randomUUID())
  const add = useFinanceChange((b: unknown) => post<ExpenseOut>('/expenses', b, key))
  return (
    <Card className="grid gap-2 sm:grid-cols-3 sm:items-end">
      <TextInput
        label={t('finance.amount')}
        inputMode="numeric"
        value={d.amount}
        onChange={(e) => setD({ ...d, amount: e.target.value })}
      />
      <SelectInput
        label={t('finance.category')}
        value={category}
        onChange={(e) => setD({ ...d, category: e.target.value })}
      >
        {categories.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </SelectInput>
      <SelectInput
        label={t('finance.paidFrom')}
        value={account}
        onChange={(e) => setD({ ...d, account: e.target.value })}
      >
        {accounts.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name}
          </option>
        ))}
      </SelectInput>
      <TextInput
        label={t('finance.date')}
        type="date"
        value={d.on}
        onChange={(e) => setD({ ...d, on: e.target.value })}
      />
      <TextInput
        label={t('finance.payee')}
        value={d.payee}
        maxLength={120}
        onChange={(e) => setD({ ...d, payee: e.target.value })}
      />
      <Button
        disabled={!ok || add.isPending}
        onClick={() =>
          add.mutate(body, {
            onSuccess: () => (setD({ ...d, amount: '', payee: '' }), setKey(crypto.randomUUID())),
          })
        }
      >
        {t('finance.addExpense')}
      </Button>
      {add.error ? <Alert>{errorMessage(add.error, t)}</Alert> : null}
    </Card>
  )
}

/** The expense being typed and the request body once it is complete. */
function useExpenseDraft(outletId: string, currency: string) {
  const accounts = (useAccounts().data ?? []).filter((a) => a.is_active)
  const categories = (useExpenseCategories().data ?? []).filter((c) => c.is_active)
  const [d, setD] = useState({ account: '', category: '', on: todayIso(), amount: '', payee: '' })
  const amount = parseMoney(d.amount, currency)
  const account = pick(d.account, accounts)
  const category = pick(d.category, categories)
  const ok = amount !== null && amount > 0 && account !== '' && category !== ''
  const body = {
    outlet_id: outletId,
    account_id: account,
    category_id: category,
    spent_on: d.on,
    amount,
    payee: d.payee.trim() || null,
  }
  return { accounts, categories, d, setD, account, category, ok, body }
}

const pick = (chosen: string, list: { id: string }[]) => chosen || list[0]?.id || ''
