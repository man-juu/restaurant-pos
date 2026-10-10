import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../../components/form'
import { Alert, Button, Card } from '../../../components/ui'
import type { GlAccountOut } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { formatMoney, intlLocale } from '../../../lib/format'
import { useGlAction } from './glApi'

type Draft = { account_id: string; debit: string; credit: string }
const blank = (): Draft => ({ account_id: '', debit: '', credit: '' })
const amount = (v: string) => Number(v.replace(/\D/g, '')) || 0

/** FR-FIN-004: a manual journal; it is saved only when debits equal credits. */
export function JournalForm({
  accounts,
  currency,
  onDone,
}: {
  accounts: GlAccountOut[]
  currency: string
  onDone: () => void
}) {
  const { t, i18n } = useTranslation()
  const act = useGlAction()
  const [day, setDay] = useState(() => new Date().toISOString().slice(0, 10))
  const [memo, setMemo] = useState('')
  const [lines, setLines] = useState<Draft[]>([blank(), blank()])
  const set = (i: number, patch: Partial<Draft>) =>
    setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))
  const debit = lines.reduce((s, l) => s + amount(l.debit), 0)
  const credit = lines.reduce((s, l) => s + amount(l.credit), 0)
  const ready = debit > 0 && debit === credit && lines.every((l) => l.account_id)
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const submit = () =>
    act.mutate(
      {
        path: 'journals',
        body: {
          entry_date: day,
          memo: memo.trim() || null,
          lines: lines.map((l) => ({
            account_id: l.account_id,
            debit: amount(l.debit),
            credit: amount(l.credit),
          })),
        },
      },
      { onSuccess: onDone },
    )
  return (
    <Card className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput
          label={t('books.date')}
          type="date"
          value={day}
          onChange={(e) => setDay(e.target.value)}
        />
        <TextInput
          label={t('books.memo')}
          value={memo}
          maxLength={500}
          onChange={(e) => setMemo(e.target.value)}
        />
      </div>
      {lines.map((l, i) => (
        <div key={i} className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr]">
          <SelectInput
            label={t('books.account')}
            value={l.account_id}
            onChange={(e) => set(i, { account_id: e.target.value })}
          >
            <option value="">{t('books.pickAccount')}</option>
            {accounts
              .filter((a) => a.is_active)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {`${a.code} ${a.name}`}
                </option>
              ))}
          </SelectInput>
          <TextInput
            label={t('books.debit')}
            inputMode="numeric"
            value={l.debit}
            onChange={(e) => set(i, { debit: e.target.value, credit: '' })}
          />
          <TextInput
            label={t('books.credit')}
            inputMode="numeric"
            value={l.credit}
            onChange={(e) => set(i, { credit: e.target.value, debit: '' })}
          />
        </div>
      ))}
      <p className={debit === credit ? 'text-sm text-muted' : 'text-sm text-danger'}>
        {t('books.totals', { debit: money(debit), credit: money(credit) })}
      </p>
      {act.error && <Alert>{errorMessage(act.error, t)}</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button variant="ghost" onClick={() => setLines([...lines, blank()])}>
          {t('books.addLine')}
        </Button>
        <Button onClick={submit} disabled={!ready || act.isPending}>
          {t('books.save')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('books.close')}
        </Button>
      </div>
    </Card>
  )
}
