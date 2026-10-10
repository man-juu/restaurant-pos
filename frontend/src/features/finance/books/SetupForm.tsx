import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../../components/form'
import { Alert, Button, Card } from '../../../components/ui'
import { errorMessage } from '../../../lib/errors'
import { useGlAction } from './glApi'

const amount = (v: string) => Number(v.replace(/\D/g, '')) || 0

/** FR-FIN-009: start the books on a date with the cash and bank you have then. Other opening
 *  balances (stock, payables, equipment) can be entered as journals on the same day. */
export function SetupForm({ canSetup }: { canSetup: boolean }) {
  const { t } = useTranslation()
  const act = useGlAction()
  const [start, setStart] = useState(() => `${new Date().toISOString().slice(0, 8)}01`)
  const [cash, setCash] = useState('')
  const [bank, setBank] = useState('')
  if (!canSetup) return <p className="text-ink-soft">{t('books.notSetUp')}</p>
  const opening = [
    { account_code: '1-1100', debit: amount(cash) },
    { account_code: '1-1200', debit: amount(bank) },
  ].filter((o) => o.debit > 0)
  return (
    <Card className="flex flex-col gap-3">
      <p>{t('books.setupHelp')}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <TextInput
          label={t('books.start')}
          type="date"
          value={start}
          onChange={(e) => setStart(e.target.value)}
        />
        <TextInput
          label={t('books.openingCash')}
          inputMode="numeric"
          value={cash}
          onChange={(e) => setCash(e.target.value)}
        />
        <TextInput
          label={t('books.openingBank')}
          inputMode="numeric"
          value={bank}
          onChange={(e) => setBank(e.target.value)}
        />
      </div>
      {act.error && <Alert>{errorMessage(act.error, t)}</Alert>}
      <Button
        className="self-start"
        disabled={!start || act.isPending}
        onClick={() => act.mutate({ path: 'setup', body: { start_date: start, opening } })}
      >
        {t('books.startBooks')}
      </Button>
    </Card>
  )
}
