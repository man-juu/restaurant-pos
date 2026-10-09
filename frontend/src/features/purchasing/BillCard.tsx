import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, StateBadge } from '../../components/ui'
import type { VendorBillOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatDate, formatMoney, intlLocale } from '../../lib/format'
import { useApAction, usePayBill, useReturns } from './apApi'

export type BillCan = { manage: boolean; pay: boolean }
type Props = {
  bill: VendorBillOut
  vendor: string
  currency: string
  can: BillCan
  methods: string[]
}

/** One bill: match findings, payments and the actions the caller may take. */
export function BillCard({ bill, vendor, currency, can, methods }: Props) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const money = (v: number) => formatMoney(v, currency, locale)
  const open = bill.status === 'open' || bill.status === 'partially_paid'
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-line bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-bold">{`${bill.number} · ${vendor} · ${bill.vendor_invoice_no}`}</p>
          <p className="text-sm text-muted">
            {t('purchasing.bills.line', {
              due: formatDate(bill.due_date, locale),
              total: money(bill.total),
              balance: money(bill.balance),
            })}
          </p>
        </div>
        <div className="flex gap-2">
          <StateBadge
            state={bill.match_status}
            label={t(`purchasing.bills.match.${bill.match_status}`)}
          />
          <StateBadge state={bill.status} label={t(`purchasing.bills.status.${bill.status}`)} />
        </div>
      </div>
      {bill.match_notes.map((n) => (
        <p key={n.item_id} className="text-sm text-danger">
          {t(`purchasing.bills.issue.${n.issue}`, {
            billed: Number(n.billed_qty),
            received: Number(n.received_qty),
            price: Number(n.billed_unit_price),
            po: Number(n.po_unit_price ?? 0),
          })}
        </p>
      ))}
      {open && can.pay && <PayRow bill={bill} methods={methods} />}
      {open && can.manage && <CreditRow bill={bill} />}
    </li>
  )
}

function PayRow({ bill, methods }: { bill: VendorBillOut; methods: string[] }) {
  const { t } = useTranslation()
  const pay = usePayBill()
  const [key, setKey] = useState(() => crypto.randomUUID())
  const [amount, setAmount] = useState(String(bill.balance))
  const [picked, setMethod] = useState('')
  const method = picked || methods[0] || '' // settings may load after this row
  const [ref, setRef] = useState('')
  const submit = () =>
    pay.mutate(
      {
        id: bill.id,
        key,
        body: {
          paid_on: new Date().toISOString().slice(0, 10),
          amount: Number(amount.replace(/\D/g, '')),
          method,
          reference: ref.trim() || null,
        },
      },
      { onSuccess: () => setKey(crypto.randomUUID()) },
    )
  return (
    <div className="flex flex-wrap items-end gap-2">
      <TextInput
        label={t('purchasing.bills.amount')}
        inputMode="numeric"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
      />
      <SelectInput
        label={t('purchasing.bills.method')}
        value={method}
        onChange={(e) => setMethod(e.target.value)}
      >
        {methods.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </SelectInput>
      <TextInput
        label={t('purchasing.bills.reference')}
        value={ref}
        maxLength={120}
        onChange={(e) => setRef(e.target.value)}
      />
      <Button onClick={submit} disabled={!method || pay.isPending}>
        {t('purchasing.bills.pay')}
      </Button>
      {pay.error && <Alert>{errorMessage(pay.error, t)}</Alert>}
    </div>
  )
}

function CreditRow({ bill }: { bill: VendorBillOut }) {
  const { t } = useTranslation()
  const returns = useReturns(bill.outlet_id)
  const action = useApAction()
  const credits = returns.data?.filter(
    (r) =>
      r.vendor_id === bill.vendor_id &&
      r.credit_note_number &&
      !r.applied_bill_id &&
      r.status === 'posted',
  )
  return (
    <div className="flex flex-wrap gap-2">
      {credits?.map((r) => (
        <Button
          key={r.id}
          variant="ghost"
          disabled={action.isPending}
          onClick={() =>
            action.mutate({ path: `bills/${bill.id}/credits`, body: { return_id: r.id } })
          }
        >
          {t('purchasing.bills.applyCredit', { no: r.credit_note_number })}
        </Button>
      ))}
      {bill.paid === 0 && bill.credited === 0 && (
        <Button
          variant="ghost"
          disabled={action.isPending}
          onClick={() => action.mutate({ path: `bills/${bill.id}/void` })}
        >
          {t('purchasing.bills.void')}
        </Button>
      )}
      {action.error ? <Alert>{errorMessage(action.error, t)}</Alert> : null}
    </div>
  )
}
