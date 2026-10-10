import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../../components/form'
import { Alert, Button, StateBadge } from '../../../components/ui'
import type { InvoiceOut } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { formatDate, formatMoney, intlLocale } from '../../../lib/format'
import { todayIso } from '../../catalog/labels'
import { useReceive, useVoidInvoice } from './arApi'

/** One wholesale invoice: what is owed, and receiving or voiding it. */
export function InvoiceCard({
  inv,
  currency,
  canManage,
  methods,
}: {
  inv: InvoiceOut
  currency: string
  canManage: boolean
  methods: string[]
}) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const money = (v: number) => formatMoney(v, currency, locale)
  const voider = useVoidInvoice()
  const open = inv.status === 'open' || inv.status === 'partially_paid'
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-line bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-bold">{`${inv.number} · ${inv.customer_name}`}</p>
          <p className="text-sm text-muted">
            {t('ar.line', {
              due: formatDate(inv.due_date, locale),
              total: money(inv.total),
              balance: money(inv.balance),
            })}
          </p>
        </div>
        <StateBadge state={inv.status} label={t(`ar.status.${inv.status}`)} />
      </div>
      {open && canManage && <ReceiveRow inv={inv} methods={methods} />}
      {open && canManage && inv.paid === 0 && (
        <Button
          variant="ghost"
          className="self-start"
          disabled={voider.isPending}
          onClick={() => voider.mutate(inv.id)}
        >
          {t('ar.void')}
        </Button>
      )}
      {voider.error && <Alert>{errorMessage(voider.error, t)}</Alert>}
    </li>
  )
}

function ReceiveRow({ inv, methods }: { inv: InvoiceOut; methods: string[] }) {
  const { t } = useTranslation()
  const receive = useReceive()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [amount, setAmount] = useState(String(inv.balance))
  const [picked, setMethod] = useState('')
  const method = picked || methods[0] || ''
  const submit = () =>
    receive.mutate(
      {
        id: inv.id,
        key,
        body: { paid_on: todayIso(), amount: Number(amount.replace(/\D/g, '')), method },
      },
      { onSuccess: () => setKey(crypto.randomUUID()) },
    )
  return (
    <div className="flex flex-wrap items-end gap-2">
      <TextInput
        label={t('ar.amount')}
        inputMode="numeric"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
      />
      <SelectInput
        label={t('ar.method')}
        value={method}
        onChange={(e) => setMethod(e.target.value)}
      >
        {methods.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </SelectInput>
      <Button onClick={submit} disabled={!method || receive.isPending}>
        {t('ar.receive')}
      </Button>
      {receive.error && <Alert>{errorMessage(receive.error, t)}</Alert>}
    </div>
  )
}
