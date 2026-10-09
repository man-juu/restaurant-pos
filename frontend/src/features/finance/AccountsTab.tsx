import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { parseMoney } from '../../lib/money'
import { todayIso } from '../catalog/labels'
import { post, useAccounts, useExpenseCategories, useFinanceChange } from './financeApi'

const KINDS = ['cash', 'bank', 'petty_cash'] as const

/** FR-FIN-001: cash and bank accounts with balances, expense categories, moving money. */
export function AccountsTab({
  currency,
  canManage,
  canMove,
}: {
  currency: string
  canManage: boolean
  canMove: boolean
}) {
  const { t, i18n } = useTranslation()
  const accounts = useAccounts()
  const categories = useExpenseCategories().data ?? []
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  return (
    <div className="flex flex-col gap-4">
      {accounts.error && <Alert>{errorMessage(accounts.error, t)}</Alert>}
      <ul className="grid gap-2 sm:grid-cols-2">
        {accounts.data?.map((a) => (
          <li
            key={a.id}
            className="flex items-center justify-between rounded-xl border border-line px-3 py-2"
          >
            <span>
              <b>{a.name}</b>{' '}
              <span className="text-sm text-ink-soft">{t(`finance.kinds.${a.kind}`)}</span>
            </span>
            <span className="font-bold tabular-nums">{money(a.balance)}</span>
          </li>
        ))}
      </ul>
      {canMove && <TransferForm currency={currency} />}
      {canManage && <NewAccount />}
      <p className="text-sm text-ink-soft">
        {t('finance.categoriesList', { names: categories.map((c) => c.name).join(', ') || '—' })}
      </p>
      {canManage && <NewCategory />}
    </div>
  )
}

function TransferForm({ currency }: { currency: string }) {
  const { t } = useTranslation()
  const accounts = (useAccounts().data ?? []).filter((a) => a.is_active)
  const move = useFinanceChange((body: unknown) => post('/transfers', body))
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [text, setText] = useState('')
  const amount = parseMoney(text, currency)
  const ok = from && to && from !== to && amount !== null && amount > 0
  const pick = (label: string, value: string, set: (v: string) => void) => (
    <SelectInput label={label} value={value} onChange={(e) => set(e.target.value)}>
      <option value="">{t('finance.choose')}</option>
      {accounts.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name}
        </option>
      ))}
    </SelectInput>
  )
  return (
    <Card className="grid gap-2 sm:grid-cols-4 sm:items-end">
      {pick(t('finance.from'), from, setFrom)}
      {pick(t('finance.to'), to, setTo)}
      <TextInput
        label={t('finance.amount')}
        inputMode="numeric"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <Button
        disabled={!ok || move.isPending}
        onClick={() =>
          move.mutate(
            { from_account_id: from, to_account_id: to, amount, moved_on: todayIso() },
            { onSuccess: () => setText('') },
          )
        }
      >
        {t('finance.move')}
      </Button>
      {move.error ? <Alert>{errorMessage(move.error, t)}</Alert> : null}
    </Card>
  )
}

function NewAccount() {
  const { t } = useTranslation()
  const add = useFinanceChange((body: unknown) => post('/accounts', body))
  const [name, setName] = useState('')
  const [kind, setKind] = useState<(typeof KINDS)[number]>('cash')
  return (
    <div className="flex flex-wrap items-end gap-2">
      <TextInput
        label={t('finance.accountName')}
        value={name}
        maxLength={80}
        onChange={(e) => setName(e.target.value)}
      />
      <SelectInput
        label={t('finance.kind')}
        value={kind}
        onChange={(e) => setKind(e.target.value as (typeof KINDS)[number])}
      >
        {KINDS.map((k) => (
          <option key={k} value={k}>
            {t(`finance.kinds.${k}`)}
          </option>
        ))}
      </SelectInput>
      <Button
        variant="ghost"
        disabled={!name.trim()}
        onClick={() => add.mutate({ name: name.trim(), kind }, { onSuccess: () => setName('') })}
      >
        {t('finance.addAccount')}
      </Button>
      {add.error ? <Alert>{errorMessage(add.error, t)}</Alert> : null}
    </div>
  )
}

function NewCategory() {
  const { t } = useTranslation()
  const add = useFinanceChange((body: unknown) => post('/categories', body))
  const [name, setName] = useState('')
  return (
    <div className="flex flex-wrap items-end gap-2">
      <TextInput
        label={t('finance.categoryName')}
        value={name}
        maxLength={80}
        onChange={(e) => setName(e.target.value)}
      />
      <Button
        variant="ghost"
        disabled={!name.trim()}
        onClick={() => add.mutate({ name: name.trim() }, { onSuccess: () => setName('') })}
      >
        {t('finance.addCategory')}
      </Button>
      {add.error ? <Alert>{errorMessage(add.error, t)}</Alert> : null}
    </div>
  )
}
