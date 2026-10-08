import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { ItemSummary, OutletOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { ComponentPicker } from '../catalog/ComponentPicker'
import { useRequestTransfer } from './api'

const QTY = /^\d{1,14}([.,]\d{1,4})?$/

interface Line {
  item_id: string
  label: string
  qty: string
}

/** FR-TRF-001: this outlet asks another outlet (usually the central kitchen) for stock. */
export function RequestForm({
  outletId,
  outlets,
  onDone,
}: {
  outletId: string
  outlets: OutletOut[]
  onDone: () => void
}) {
  const { t } = useTranslation()
  const ask = useRequestTransfer()
  const sources = outlets.filter((o) => o.is_active && o.id !== outletId)
  const [from, setFrom] = useState(sources[0]?.id ?? '')
  const [lines, setLines] = useState<Line[]>([])
  const [key] = useState(() => crypto.randomUUID())
  const ok =
    from &&
    lines.length > 0 &&
    lines.every((l) => QTY.test(l.qty) && Number(l.qty.replace(',', '.')) > 0)
  const add = (item: ItemSummary) =>
    setLines([...lines, { item_id: item.id, label: item.name, qty: '' }])
  const submit = () =>
    ask.mutate(
      {
        body: {
          from_outlet_id: from,
          to_outlet_id: outletId,
          lines: lines.map((l) => ({ item_id: l.item_id, qty: l.qty.replace(',', '.') })),
        },
        key,
      },
      { onSuccess: onDone },
    )
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-bold">{t('transfers.new')}</h2>
      <SelectInput
        label={t('transfers.from')}
        value={from}
        onChange={(e) => setFrom(e.target.value)}
      >
        {sources.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </SelectInput>
      {lines.map((l, i) => (
        <TextInput
          key={l.item_id}
          label={t('transfers.qtyOf', { name: l.label })}
          inputMode="decimal"
          value={l.qty}
          onChange={(e) =>
            setLines(lines.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))
          }
        />
      ))}
      <ComponentPicker
        exclude={new Set(lines.map((l) => l.item_id))}
        onPick={add}
        label={t('transfers.add')}
      />
      {ask.error ? <Alert>{errorMessage(ask.error, t)}</Alert> : null}
      <div className="flex gap-2">
        <Button disabled={!ok || ask.isPending} onClick={submit}>
          {t('transfers.send')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('catalog.back')}
        </Button>
      </div>
    </Card>
  )
}
