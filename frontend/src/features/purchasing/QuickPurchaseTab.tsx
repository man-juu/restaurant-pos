import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { ItemSummary } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { useUnits } from '../catalog/api'
import { ComponentPicker } from '../catalog/ComponentPicker'
import { todayIso } from '../catalog/labels'
import { useQuickPurchase, useVendors } from './api'
import { InvoicePhoto } from './InvoicePhoto'
import { QuickLines } from './QuickLines'
import { lineInvalid, type QuickLineDraft, quickTotal, toQuickBody } from './quickDraft'

/** FR-PUR-004: what was bought at the market or paid in cash, received in one step. */
export function QuickPurchaseTab({ outletId, currency }: { outletId: string; currency: string }) {
  const { t, i18n } = useTranslation()
  const units = useUnits()
  const vendors = useVendors()
  const buy = useQuickPurchase()
  const [vendorId, setVendorId] = useState('')
  const [vendorName, setVendorName] = useState('')
  const [date, setDate] = useState(todayIso)
  const [invoice, setInvoice] = useState<string>()
  const [lines, setLines] = useState<QuickLineDraft[]>([])
  const [key, setKey] = useState(() => crypto.randomUUID())
  const invalid = lines.length === 0 || lines.some((ln) => lineInvalid(ln, currency))
  const add = (item: ItemSummary) =>
    setLines([
      ...lines,
      {
        item_id: item.id,
        label: item.name,
        qty: '',
        unit_id: item.base_unit_id,
        total: '',
        expiry: '',
      },
    ])
  const submit = () =>
    buy.mutate(
      {
        body: toQuickBody({ outletId, vendorId, vendorName, date, invoice }, lines, currency),
        key,
      },
      { onSuccess: () => (setLines([]), setKey(crypto.randomUUID())) }, // a new purchase, a new key
    )

  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('purchasing.quick.help')}</p>
      <div className="grid gap-3 sm:grid-cols-3">
        <SelectInput
          label={t('purchasing.quick.vendor')}
          value={vendorId}
          onChange={(e) => setVendorId(e.target.value)}
        >
          <option value="">{t('purchasing.quick.noVendor')}</option>
          {vendors.data
            ?.filter((v) => v.is_active)
            .map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
        </SelectInput>
        {!vendorId && (
          <TextInput
            label={t('purchasing.quick.where')}
            value={vendorName}
            maxLength={200}
            onChange={(e) => setVendorName(e.target.value)}
          />
        )}
        <TextInput
          label={t('inventory.opening.date')}
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </div>
      <ComponentPicker
        exclude={new Set(lines.map((l) => l.item_id))}
        onPick={add}
        label={t('purchasing.quick.add')}
      />
      <QuickLines lines={lines} units={units.data ?? []} currency={currency} onChange={setLines} />
      <InvoicePhoto onUploaded={setInvoice} />
      {buy.error ? <Alert>{errorMessage(buy.error, t)}</Alert> : null}
      {buy.isSuccess && (
        <p className="font-semibold text-good">
          {t('purchasing.quick.done', { number: buy.data.number })}
        </p>
      )}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-semibold">
          {t('purchasing.quick.total', {
            total: formatMoney(quickTotal(lines, currency), currency, intlLocale(i18n.language)),
          })}
        </span>
        <Button onClick={submit} disabled={invalid || buy.isPending} aria-busy={buy.isPending}>
          {t('purchasing.quick.save')}
        </Button>
      </div>
    </Card>
  )
}
