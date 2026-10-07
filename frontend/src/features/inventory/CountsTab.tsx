import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, SelectInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { ComponentPicker } from '../catalog/ComponentPicker'
import { todayIso } from '../catalog/labels'
import { CountSheet } from './CountSheet'
import { useDocuments, useStartCount } from './docApi'
import { DocList } from './DocList'

const TYPES = ['full', 'spot', 'cycle'] as const
type CountType = (typeof TYPES)[number]
const STOCK_TYPES = ['ingredient', 'semi_finished', 'menu'] as const

/** FR-INV-007: counts list, starting a count, and the count sheet. */
export function CountsTab({ outletId, canApprove }: { outletId: string; canApprove: boolean }) {
  const { t } = useTranslation()
  const docs = useDocuments('counts', outletId)
  const [open, setOpen] = useState<string>()

  if (open)
    return <CountSheet countId={open} canApprove={canApprove} onClose={() => setOpen(undefined)} />
  return (
    <div className="flex flex-col gap-4">
      <StartCount outletId={outletId} onStarted={setOpen} />
      <DocList
        docs={docs.data ?? []}
        actions={(d) => (
          <Button variant="ghost" onClick={() => setOpen(d.id)}>
            {t('inventory.docs.open')}
          </Button>
        )}
      />
    </div>
  )
}

function StartCount({
  outletId,
  onStarted,
}: {
  outletId: string
  onStarted: (id: string) => void
}) {
  const { t } = useTranslation()
  const start = useStartCount()
  const [type, setType] = useState<CountType>('full')
  const [blind, setBlind] = useState(true)
  const [items, setItems] = useState<{ id: string; label: string }[]>([])
  const needsItems = type !== 'full' && items.length === 0
  const body = {
    outlet_id: outletId,
    business_date: todayIso(),
    count_type: type,
    blind,
    item_ids: items.map((i) => i.id),
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2 sm:items-end">
        <SelectInput
          label={t('inventory.docs.countType')}
          value={type}
          onChange={(e) => setType(e.target.value as CountType)}
        >
          {TYPES.map((k) => (
            <option key={k} value={k}>
              {t(`inventory.countTypes.${k}`)}
            </option>
          ))}
        </SelectInput>
        <CheckInput label={t('inventory.docs.blind')} checked={blind} onChange={setBlind} />
      </div>
      {items.length > 0 && <p className="text-sm">{items.map((i) => i.label).join(', ')}</p>}
      {type !== 'full' && (
        <ComponentPicker
          label={t('inventory.opening.add')}
          types={STOCK_TYPES}
          exclude={new Set(items.map((i) => i.id))}
          onPick={(item) => setItems([...items, { id: item.id, label: item.name }])}
        />
      )}
      <div>
        <Button
          onClick={() => start.mutate(body, { onSuccess: (doc) => onStarted(doc.id) })}
          disabled={needsItems || start.isPending}
        >
          {t('inventory.docs.startCount')}
        </Button>
      </div>
      {start.error ? <Alert>{errorMessage(start.error, t)}</Alert> : null}
    </Card>
  )
}
