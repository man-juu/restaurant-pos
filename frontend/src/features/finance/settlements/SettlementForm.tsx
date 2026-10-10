import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../../components/form'
import { Alert, Button, Card } from '../../../components/ui'
import { errorMessage } from '../../../lib/errors'
import { formatMoney, intlLocale } from '../../../lib/format'
import { todayIso } from '../../catalog/labels'
import { useAccounts } from '../financeApi'
import { useCreateSettlement } from './settlementApi'

const AMOUNTS = ['gross', 'commission', 'fees', 'adjustments'] as const
type Amounts = Record<(typeof AMOUNTS)[number], string>
const num = (v: string) => (v.trim().startsWith('-') ? -1 : 1) * Number(v.replace(/\D/g, ''))

/** FR-FIN-007: copy one payout statement; the payout is worked out from its parts. */
export function SettlementForm(props: {
  channelId: string
  outletId: string
  from: string
  to: string
  currency: string
  onDone: () => void
}) {
  const { t, i18n } = useTranslation()
  const banks = (useAccounts().data ?? []).filter((a) => a.is_active && a.kind === 'bank')
  const [picked, setAccount] = useState('')
  const accountId = picked || banks[0]?.id || ''
  const [paidOn, setPaidOn] = useState(todayIso)
  const [ref, setRef] = useState('')
  const [v, setV] = useState<Amounts>({ gross: '', commission: '', fees: '', adjustments: '' })
  const [key] = useState(() => crypto.randomUUID())
  const create = useCreateSettlement()
  const payout = num(v.gross) - num(v.commission) - num(v.fees) + num(v.adjustments)
  const submit = () =>
    create.mutate(
      {
        key,
        body: {
          channel_id: props.channelId,
          outlet_id: props.outletId,
          account_id: accountId,
          period_from: props.from,
          period_to: props.to,
          paid_on: paidOn,
          gross: num(v.gross),
          commission: num(v.commission),
          fees: num(v.fees),
          adjustments: num(v.adjustments),
          payout,
          reference: ref.trim() || null,
        },
      },
      { onSuccess: props.onDone },
    )
  return (
    <Card className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {AMOUNTS.map((k) => (
          <TextInput
            key={k}
            label={t(`settle.${k}`)}
            inputMode="numeric"
            value={v[k]}
            onChange={(e) => setV({ ...v, [k]: e.target.value })}
          />
        ))}
        <SelectInput
          label={t('settle.account')}
          value={accountId}
          onChange={(e) => setAccount(e.target.value)}
        >
          {banks.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </SelectInput>
        <TextInput
          label={t('settle.paidOn')}
          type="date"
          value={paidOn}
          onChange={(e) => setPaidOn(e.target.value)}
        />
        <TextInput
          label={t('settle.reference')}
          value={ref}
          maxLength={120}
          onChange={(e) => setRef(e.target.value)}
        />
      </div>
      <p className="font-bold">
        {t('settle.payout', {
          amount: formatMoney(payout, props.currency, intlLocale(i18n.language)),
        })}
      </p>
      <Button onClick={submit} disabled={!accountId || payout < 0 || create.isPending}>
        {t('settle.save')}
      </Button>
      {!banks.length && <Alert>{t('settle.noBank')}</Alert>}
      {create.error && <Alert>{errorMessage(create.error, t)}</Alert>}
    </Card>
  )
}
