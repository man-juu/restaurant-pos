import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { BaseLine } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useReceipts, useVendors } from './api'
import { fetchReceiptLines, useCreateReturn } from './apApi'

const REASONS = ['damaged', 'expired', 'wrong_item', 'quality', 'other'] as const
const today = () => new Date().toISOString().slice(0, 10)

/** FR-PUR-008: send back part of a receipt; the credit defaults to the price paid. */
export function ReturnForm({ outletId, onDone }: { outletId: string; onDone: () => void }) {
  const { t, i18n } = useTranslation()
  const vendors = useVendors()
  const receipts = useReceipts(outletId)
  const create = useCreateReturn()
  const [key] = useState(() => crypto.randomUUID())
  const [receiptId, setReceiptId] = useState('')
  const [lines, setLines] = useState<BaseLine[]>([])
  const [qty, setQty] = useState<Record<string, string>>({})
  const [reason, setReason] = useState<(typeof REASONS)[number]>('damaged')
  const [day, setDay] = useState(today)
  const receipt = receipts.data?.find((r) => r.id === receiptId)
  const vendorName = (id: string | null) => vendors.data?.find((v) => v.id === id)?.name ?? ''
  const pick = async (id: string) => {
    setReceiptId(id)
    setQty({})
    setLines(id ? await fetchReceiptLines(id, i18n.language) : [])
  }
  const chosen = lines
    .map((ln) => ({ item_id: ln.item_id, qty: (qty[ln.item_id] ?? '').replace(',', '.') }))
    .filter((ln) => Number(ln.qty) > 0)
  const submit = () =>
    receipt?.vendor_id &&
    create.mutate(
      {
        body: {
          outlet_id: outletId,
          vendor_id: receipt.vendor_id,
          receipt_id: receipt.id,
          business_date: day,
          reason,
          lines: chosen,
        },
        key,
      },
      { onSuccess: onDone },
    )
  return (
    <Card className="flex flex-col gap-3">
      <SelectInput
        label={t('purchasing.returns.receipt')}
        value={receiptId}
        onChange={(e) => void pick(e.target.value)}
      >
        <option value="">{t('purchasing.returns.pickReceipt')}</option>
        {receipts.data
          ?.filter((r) => r.status === 'posted' && r.vendor_id)
          .map((r) => (
            <option key={r.id} value={r.id}>
              {`${r.number} · ${vendorName(r.vendor_id)}`}
            </option>
          ))}
      </SelectInput>
      {lines.map((ln) => (
        <TextInput
          key={ln.item_id}
          label={t('purchasing.returns.qtyOf', { name: ln.name, have: ln.qty, unit: ln.unit_code })}
          inputMode="decimal"
          value={qty[ln.item_id] ?? ''}
          onChange={(e) => setQty({ ...qty, [ln.item_id]: e.target.value })}
        />
      ))}
      <SelectInput
        label={t('purchasing.returns.reason')}
        value={reason}
        onChange={(e) => setReason(e.target.value as (typeof REASONS)[number])}
      >
        {REASONS.map((r) => (
          <option key={r} value={r}>
            {t(`purchasing.returns.reasons.${r}`)}
          </option>
        ))}
      </SelectInput>
      <TextInput
        label={t('purchasing.returns.date')}
        type="date"
        value={day}
        onChange={(e) => setDay(e.target.value)}
      />
      {create.error && <Alert>{errorMessage(create.error, t)}</Alert>}
      <div className="flex gap-2">
        <Button onClick={submit} disabled={!chosen.length || create.isPending}>
          {t('purchasing.returns.post')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('purchasing.ap.cancel')}
        </Button>
      </div>
    </Card>
  )
}
