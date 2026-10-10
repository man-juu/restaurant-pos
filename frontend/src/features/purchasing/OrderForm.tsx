import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { ItemSummary } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { parseMoney } from '../../lib/money'
import { useUnits } from '../catalog/api'
import { ComponentPicker } from '../catalog/ComponentPicker'
import { todayIso } from '../catalog/labels'
import { useVendors } from './api'
import { useSaveOrder } from './orderApi'

interface Line {
  item_id: string
  label: string
  qty: string
  unit_id: string
  price: string
}

const QTY = /^\d{1,14}([.,]\d{1,4})?$/

/** FR-PUR-003: a draft order to one vendor; submitting it starts approval if a rule applies. */
export function OrderForm({
  outletId,
  currency,
  onDone,
}: {
  outletId: string
  currency: string
  onDone: () => void
}) {
  const { t } = useTranslation()
  const vendors = useVendors()
  const units = useUnits()
  const save = useSaveOrder()
  const [vendorId, setVendorId] = useState('')
  const [expected, setExpected] = useState('')
  const [lines, setLines] = useState<Line[]>([])
  const update = (i: number, patch: Partial<Line>) =>
    setLines(lines.map((ln, j) => (j === i ? { ...ln, ...patch } : ln)))
  const bad = (ln: Line) => !QTY.test(ln.qty) || parseMoney(ln.price, currency) === null
  const invalid = !vendorId || lines.length === 0 || lines.some(bad)
  const add = (item: ItemSummary) =>
    setLines([
      ...lines,
      { item_id: item.id, label: item.name, qty: '', unit_id: item.base_unit_id, price: '' },
    ])
  const submit = () =>
    save.mutate(
      {
        body: {
          outlet_id: outletId,
          vendor_id: vendorId,
          order_date: todayIso(),
          expected_date: expected || null,
          lines: lines.map((ln) => ({
            item_id: ln.item_id,
            qty: ln.qty.replace(',', '.'),
            unit_id: ln.unit_id,
            unit_price: parseMoney(ln.price, currency) ?? 0,
          })),
        },
      },
      { onSuccess: onDone },
    )
  return (
    <Card className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectInput
          label={t('purchasing.quick.vendor')}
          value={vendorId}
          onChange={(e) => setVendorId(e.target.value)}
        >
          <option value="">{t('purchasing.orders.pickVendor')}</option>
          {vendors.data
            ?.filter((v) => v.is_active)
            .map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
        </SelectInput>
        <TextInput
          label={t('purchasing.orders.expected')}
          type="date"
          value={expected}
          onChange={(e) => setExpected(e.target.value)}
        />
      </div>
      <ComponentPicker
        exclude={new Set(lines.map((l) => l.item_id))}
        onPick={add}
        label={t('purchasing.quick.add')}
      />
      <ul className="flex flex-col gap-2">
        {lines.map((ln, i) => (
          <li
            key={ln.item_id}
            className="grid items-end gap-3 rounded-xl border border-line p-3 sm:grid-cols-4"
          >
            <p className="self-center font-semibold">{ln.label}</p>
            <TextInput
              label={t('catalog.recipe.qty')}
              inputMode="decimal"
              value={ln.qty}
              onChange={(e) => update(i, { qty: e.target.value })}
            />
            <SelectInput
              label={t('catalog.conversions.unit')}
              value={ln.unit_id}
              onChange={(e) => update(i, { unit_id: e.target.value })}
            >
              {units.data?.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.code}
                </option>
              ))}
            </SelectInput>
            <TextInput
              label={t('purchasing.orders.unitPrice', { currency })}
              inputMode="numeric"
              value={ln.price}
              onChange={(e) => update(i, { price: e.target.value })}
            />
          </li>
        ))}
      </ul>
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      <div className="flex gap-2">
        <Button onClick={submit} disabled={invalid || save.isPending} aria-busy={save.isPending}>
          {t('purchasing.orders.saveDraft')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('catalog.cancel')}
        </Button>
      </div>
    </Card>
  )
}
