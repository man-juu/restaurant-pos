import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../../components/form'
import { Alert, Button, Card } from '../../../components/ui'
import type { CustomerOut, ItemSummary } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { useChannels } from '../../catalog/api'
import { ComponentPicker } from '../../catalog/ComponentPicker'
import { todayIso } from '../../catalog/labels'
import { useCreateInvoice } from './arApi'
import { CustomerPick } from './CustomerPick'

type Line = { item_id: string; label: string; qty: string; price: string }
const SELLABLE = ['menu', 'ingredient', 'semi_finished'] as const
const digits = (v: string) => Number(v.replace(/\D/g, ''))

/** FR-SAL-011: invoice a wholesale customer; the due date follows the payment terms setting. */
export function InvoiceForm({ outletId, onDone }: { outletId: string; onDone: () => void }) {
  const { t } = useTranslation()
  const channels = (useChannels().data ?? []).filter((c) => c.kind === 'wholesale')
  const [picked, setChannel] = useState('')
  const channelId = picked || channels[0]?.id || ''
  const [customer, setCustomer] = useState<CustomerOut | null>(null)
  const [date, setDate] = useState(todayIso)
  const [lines, setLines] = useState<Line[]>([])
  const [key] = useState(() => crypto.randomUUID())
  const create = useCreateInvoice()
  const add = (i: ItemSummary) =>
    setLines([...lines, { item_id: i.id, label: i.name, qty: '1', price: '' }])
  const update = (i: number, patch: Partial<Line>) =>
    setLines(lines.map((ln, j) => (j === i ? { ...ln, ...patch } : ln)))
  const ready = Boolean(customer && channelId) && linesOk(lines)
  const submit = () =>
    create.mutate(
      {
        key,
        body: toBody(
          { outlet: outletId, channel: channelId, customer: customer?.id ?? '', date },
          lines,
        ),
      },
      { onSuccess: onDone },
    )
  if (!channels.length) return <Alert>{t('ar.form.noChannel')}</Alert>
  return (
    <Card className="flex flex-col gap-3">
      <CustomerPick value={customer} onPick={setCustomer} />
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectInput
          label={t('ar.form.channel')}
          value={channelId}
          onChange={(e) => setChannel(e.target.value)}
        >
          {channels.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </SelectInput>
        <TextInput
          label={t('ar.form.date')}
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </div>
      <LineRows
        lines={lines}
        update={update}
        remove={(i) => setLines(lines.filter((_, j) => j !== i))}
      />
      <ComponentPicker
        exclude={new Set(lines.map((l) => l.item_id))}
        onPick={add}
        label={t('ar.form.addItem')}
        types={SELLABLE}
      />
      <Button onClick={submit} disabled={!ready || create.isPending}>
        {t('ar.form.save')}
      </Button>
      {create.error && <Alert>{errorMessage(create.error, t)}</Alert>}
    </Card>
  )
}

const linesOk = (lines: Line[]) => lines.length > 0 && lines.every((l) => Number(l.qty) > 0)

type Head = { outlet: string; channel: string; customer: string; date: string }

function toBody(h: Head, lines: Line[]) {
  return {
    outlet_id: h.outlet,
    channel_id: h.channel,
    customer_id: h.customer,
    invoice_date: h.date,
    lines: lines.map((l) => ({
      item_id: l.item_id,
      qty: l.qty,
      unit_price: l.price ? digits(l.price) : null,
    })),
  }
}

function LineRows({
  lines,
  update,
  remove,
}: {
  lines: Line[]
  update: (i: number, patch: Partial<Line>) => void
  remove: (i: number) => void
}) {
  const { t } = useTranslation()
  return (
    <ul className="flex flex-col gap-2">
      {lines.map((ln, i) => (
        <li key={ln.item_id} className="grid items-end gap-2 sm:grid-cols-[2fr_1fr_1fr_auto]">
          <p className="self-center font-semibold">{ln.label}</p>
          <TextInput
            label={t('ar.form.qty')}
            inputMode="decimal"
            value={ln.qty}
            onChange={(e) => update(i, { qty: e.target.value })}
          />
          <TextInput
            label={t('ar.form.price')}
            inputMode="numeric"
            value={ln.price}
            onChange={(e) => update(i, { price: e.target.value })}
          />
          <Button variant="ghost" onClick={() => remove(i)}>
            {t('ar.form.remove')}
          </Button>
        </li>
      ))}
    </ul>
  )
}
