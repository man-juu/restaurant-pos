import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useUnits } from '../catalog/api'
import { todayIso } from '../catalog/labels'
import { useDecide, useDocuments, useSubmitNewAdjustment } from './docApi'
import { DocList } from './DocList'
import { ItemQtyLines } from './ItemQtyLines'
import { qtyOk, type QtyLineDraft } from './qtyLines'

const REASONS = ['correction', 'found', 'theft', 'damaged', 'other'] as const
type Reason = (typeof REASONS)[number]

/** FR-INV-009: stock changes without a physical event. Approval rules may hold them. */
export function AdjustmentsTab({
  outletId,
  canCreate,
  canApprove,
}: {
  outletId: string
  canCreate: boolean
  canApprove: boolean
}) {
  const { t } = useTranslation()
  const docs = useDocuments('adjustments', outletId)
  const decide = useDecide('adjustments')

  return (
    <div className="flex flex-col gap-4">
      {canCreate && <AdjustmentForm outletId={outletId} />}
      {decide.error ? <Alert>{errorMessage(decide.error, t)}</Alert> : null}
      <DocList
        docs={docs.data ?? []}
        actions={(d) =>
          canApprove &&
          d.status === 'submitted' && (
            <>
              <Button onClick={() => decide.mutate({ id: d.id, approve: true })}>
                {t('inventory.docs.approve')}
              </Button>
              <Button variant="ghost" onClick={() => decide.mutate({ id: d.id, approve: false })}>
                {t('inventory.docs.reject')}
              </Button>
            </>
          )
        }
      />
    </div>
  )
}

function AdjustmentForm({ outletId }: { outletId: string }) {
  const { t } = useTranslation()
  const units = useUnits()
  const submit = useSubmitNewAdjustment()
  const [reason, setReason] = useState<Reason>('correction')
  const [date, setDate] = useState(todayIso)
  const [lines, setLines] = useState<QtyLineDraft[]>([])
  const invalid = lines.length === 0 || lines.some((ln) => !qtyOk(ln.qty, true))
  const body = {
    outlet_id: outletId,
    business_date: date,
    reason_code: reason,
    lines: lines.map(({ item_id, qty, unit_id }) => ({
      item_id,
      qty: qty.replace(',', '.'),
      unit_id,
    })),
  }

  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('inventory.docs.adjustHelp')}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <SelectInput
          label={t('inventory.docs.reason')}
          value={reason}
          onChange={(e) => setReason(e.target.value as Reason)}
        >
          {REASONS.map((r) => (
            <option key={r} value={r}>
              {t(`inventory.reasons.${r}`)}
            </option>
          ))}
        </SelectInput>
        <TextInput
          label={t('inventory.docs.date')}
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
        />
      </div>
      <ItemQtyLines lines={lines} units={units.data ?? []} signed onChange={setLines} />
      <div className="flex flex-wrap items-center gap-3">
        <Button
          onClick={() => submit.mutate(body, { onSuccess: () => setLines([]) })}
          disabled={invalid || submit.isPending}
          aria-busy={submit.isPending}
        >
          {t('inventory.docs.submit')}
        </Button>
        {submit.data && (
          <span role="status" className="text-sm text-good">
            {t(`inventory.docs.result.${submit.data.status}`, { number: submit.data.number })}
          </span>
        )}
      </div>
      {submit.error ? <Alert>{errorMessage(submit.error, t)}</Alert> : null}
    </Card>
  )
}
