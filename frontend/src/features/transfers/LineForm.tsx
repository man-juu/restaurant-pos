import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button } from '../../components/ui'
import type { TransferOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { todayIso } from '../catalog/labels'
import { useTransferStep } from './api'
import { focusLine } from '../inventory/locations/focus'
import { ScanBox } from '../inventory/locations/ScanBox'

const QTY = /^\d{1,14}([.,]\d{1,4})?$/
const n = (v: string | null | undefined) => String(Number(v ?? 0))
const dot = (v: string) => v.replace(',', '.')

/** The source approves (may change quantities); the destination receives (may report
 *  shortage or damage). Same shape: one quantity per line. */
export function LineForm({
  transfer,
  mode,
}: {
  transfer: TransferOut
  mode: 'approve' | 'receive'
}) {
  const { t } = useTranslation()
  const step = useTransferStep()
  const base = (ln: TransferOut['lines'][number]) =>
    n(mode === 'approve' ? ln.requested_qty : ln.shipped_qty)
  const lines = transfer.lines.filter((ln) => mode === 'approve' || Number(ln.shipped_qty ?? 0) > 0)
  const [qty, setQty] = useState<Record<string, string>>({})
  const [why, setWhy] = useState<Record<string, string>>({})
  const changed = lines.filter((ln) => qty[ln.item_id] !== undefined && qty[ln.item_id] !== '')
  const ok = changed.every((ln) => QTY.test(qty[ln.item_id]))
  const submit = () => {
    const rows = changed.map((ln) => ({ item_id: ln.item_id, qty: dot(qty[ln.item_id]) }))
    if (mode === 'approve')
      return step.mutate({ id: transfer.id, action: 'approve', body: { lines: rows } })
    const today = todayIso()
    const withWhy = rows.map((r) => ({
      ...r,
      reason: (why[r.item_id] || null) as 'short' | 'damaged' | null,
    }))
    step.mutate({
      id: transfer.id,
      action: 'receive',
      body: { business_date: today, lines: withWhy },
    })
  }
  return (
    <div className="flex flex-col gap-3 border-t border-line pt-3">
      <h3 className="font-bold">{t(`transfers.${mode}`)}</h3>
      <ScanBox
        outletId={transfer.from_outlet_id}
        onFound={(hit) => focusLine(`tr-${hit.item_id}`)}
      />
      {lines.map((ln) => (
        <div key={ln.item_id} className="grid gap-2 sm:grid-cols-2">
          <TextInput
            label={t('transfers.lineQty', { name: ln.item_name, unit: ln.unit_code })}
            id={`tr-${ln.item_id}`}
            inputMode="decimal"
            placeholder={base(ln)}
            value={qty[ln.item_id] ?? ''}
            onChange={(e) => setQty({ ...qty, [ln.item_id]: e.target.value })}
          />
          {mode === 'receive' && (
            <SelectInput
              label={t('transfers.reason')}
              value={why[ln.item_id] ?? ''}
              onChange={(e) => setWhy({ ...why, [ln.item_id]: e.target.value })}
            >
              <option value="">{t('transfers.reasons.none')}</option>
              <option value="short">{t('transfers.reasons.short')}</option>
              <option value="damaged">{t('transfers.reasons.damaged')}</option>
            </SelectInput>
          )}
        </div>
      ))}
      <p className="text-sm text-ink-soft">{t('transfers.emptyMeansAll')}</p>
      {step.error ? <Alert>{errorMessage(step.error, t)}</Alert> : null}
      <Button className="self-start" disabled={!ok || step.isPending} onClick={submit}>
        {t(`transfers.${mode}Save`)}
      </Button>
    </div>
  )
}
