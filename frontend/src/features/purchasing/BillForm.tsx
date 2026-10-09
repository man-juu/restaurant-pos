import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { BaseLine } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useReceipts, useVendors } from './api'
import { fetchReceiptLines, useCreateBill } from './apApi'

const today = () => new Date().toISOString().slice(0, 10)

function merge(groups: BaseLine[][]): BaseLine[] {
  const out = new Map<string, BaseLine>()
  for (const ln of groups.flat()) {
    const had = out.get(ln.item_id)
    out.set(
      ln.item_id,
      had
        ? { ...had, qty: String(Number(had.qty) + Number(ln.qty)), amount: had.amount + ln.amount }
        : ln,
    )
  }
  return [...out.values()]
}

/** FR-PUR-009: enter the vendor's invoice for received goods; amounts start from receipts. */
export function BillForm({ outletId, onDone }: { outletId: string; onDone: () => void }) {
  const { t, i18n } = useTranslation()
  const vendors = useVendors()
  const receipts = useReceipts(outletId)
  const create = useCreateBill()
  const [key] = useState(() => crypto.randomUUID())
  const [vendorId, setVendorId] = useState('')
  const [invoice, setInvoice] = useState('')
  const [day, setDay] = useState(today)
  const [picked, setPicked] = useState<string[]>([])
  const [lines, setLines] = useState<BaseLine[]>([])
  const mine = receipts.data?.filter((r) => r.vendor_id === vendorId && r.status === 'posted')
  const toggle = async (id: string, on: boolean) => {
    const next = on ? [...picked, id] : picked.filter((x) => x !== id)
    setPicked(next)
    setLines(merge(await Promise.all(next.map((r) => fetchReceiptLines(r, i18n.language)))))
  }
  const poIds = new Set(mine?.filter((r) => picked.includes(r.id)).map((r) => r.po_id))
  const submit = () =>
    create.mutate(
      {
        body: {
          vendor_id: vendorId,
          vendor_invoice_no: invoice.trim(),
          outlet_id: outletId,
          po_id: poIds.size === 1 ? ([...poIds][0] ?? null) : null,
          receipt_ids: picked,
          bill_date: day,
          lines: lines.map(({ item_id, qty, amount }) => ({ item_id, qty, amount })),
        },
        key,
      },
      { onSuccess: onDone },
    )
  return (
    <Card className="flex flex-col gap-3">
      <SelectInput
        label={t('purchasing.bills.vendor')}
        value={vendorId}
        onChange={(e) => setVendorId(e.target.value)}
      >
        <option value="">{t('purchasing.bills.pickVendor')}</option>
        {vendors.data?.map((v) => (
          <option key={v.id} value={v.id}>
            {v.name}
          </option>
        ))}
      </SelectInput>
      <TextInput
        label={t('purchasing.bills.invoiceNo')}
        value={invoice}
        maxLength={80}
        onChange={(e) => setInvoice(e.target.value)}
      />
      <TextInput
        label={t('purchasing.bills.date')}
        type="date"
        value={day}
        onChange={(e) => setDay(e.target.value)}
      />
      {mine?.map((r) => (
        <CheckInput
          key={r.id}
          label={r.number}
          checked={picked.includes(r.id)}
          onChange={(on) => void toggle(r.id, on)}
        />
      ))}
      {lines.map((ln, i) => (
        <TextInput
          key={ln.item_id}
          label={t('purchasing.bills.amountOf', { name: ln.name, qty: ln.qty, unit: ln.unit_code })}
          inputMode="numeric"
          value={String(ln.amount)}
          onChange={(e) =>
            setLines(
              lines.map((x, j) =>
                j === i ? { ...x, amount: Number(e.target.value.replace(/\D/g, '')) } : x,
              ),
            )
          }
        />
      ))}
      {create.error && <Alert>{errorMessage(create.error, t)}</Alert>}
      <div className="flex gap-2">
        <Button onClick={submit} disabled={!lines.length || !invoice.trim() || create.isPending}>
          {t('purchasing.bills.save')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('purchasing.ap.cancel')}
        </Button>
      </div>
    </Card>
  )
}
