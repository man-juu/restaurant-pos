import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { parseMoney } from '../../lib/money'
import { useIssue, useVoid, useVouchers } from './api'

/** Vouchers issued by hand (a gift, an apology) and voiding unused ones. */
export function VouchersPanel({
  money,
  currency,
}: {
  money: (v: number) => string
  currency: string
}) {
  const { t } = useTranslation()
  const list = useVouchers(true)
  const voidIt = useVoid()
  return (
    <div className="flex flex-col gap-3">
      <IssueForm currency={currency} />
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {voidIt.error ? <Alert>{errorMessage(voidIt.error, t)}</Alert> : null}
      <Card>
        <ul className="flex flex-col gap-2 text-sm">
          {(list.data ?? []).map((v) => (
            <li key={v.id} className="flex items-center justify-between gap-2">
              <span>
                <span className="font-mono font-bold">{v.code}</span> · {money(v.amount)}
                {v.note ? ` · ${v.note}` : ''}
              </span>
              <Button
                variant="ghost"
                disabled={voidIt.isPending}
                onClick={() => voidIt.mutate(v.id)}
              >
                {t('loyalty.void')}
              </Button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

function IssueForm({ currency }: { currency: string }) {
  const { t } = useTranslation()
  const issue = useIssue()
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [key, setKey] = useState(() => crypto.randomUUID())
  const value = parseMoney(amount, currency)
  const submit = () =>
    issue.mutate(
      { body: { amount: value ?? 0, ...(note.trim() ? { note } : {}) }, key },
      { onSuccess: () => (setKey(crypto.randomUUID()), setAmount(''), setNote('')) },
    )
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-bold">{t('loyalty.issue')}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput
          label={t('loyalty.amount', { currency })}
          inputMode="numeric"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <TextInput
          label={t('loyalty.note')}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      {issue.error ? <Alert>{errorMessage(issue.error, t)}</Alert> : null}
      {issue.data && (
        <p className="text-sm text-good" role="status">
          {t('loyalty.made', { code: issue.data.code })}
        </p>
      )}
      <Button className="self-start" disabled={!value || issue.isPending} onClick={submit}>
        {t('loyalty.issueButton')}
      </Button>
    </Card>
  )
}
