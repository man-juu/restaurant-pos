import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useUnits } from '../catalog/api'
import { todayIso } from '../catalog/labels'
import { useDocuments, usePostWaste, useReverseWaste } from './docApi'
import { DocList } from './DocList'
import { ItemQtyLines } from './ItemQtyLines'
import { qtyOk, type QtyLineDraft } from './qtyLines'

const WASTE_REASONS = [
  'spoilage',
  'expired',
  'preparation_loss',
  'damaged',
  'staff_meal',
  'other',
] as const
type Reason = (typeof WASTE_REASONS)[number]

const toLines = (lines: QtyLineDraft[]) =>
  lines.map(({ item_id, qty, unit_id }) => ({ item_id, qty: qty.replace(',', '.'), unit_id }))

/** FR-INV-008: what was thrown away, why, and how much. Posted at once. */
export function WasteTab({ outletId, canReverse }: { outletId: string; canReverse: boolean }) {
  const { t } = useTranslation()
  const units = useUnits()
  const docs = useDocuments('waste', outletId)
  const post = usePostWaste()
  const undo = useReverseWaste()
  const [reason, setReason] = useState<Reason>('spoilage')
  const [date, setDate] = useState(todayIso)
  const [lines, setLines] = useState<QtyLineDraft[]>([])
  const invalid = lines.length === 0 || lines.some((ln) => !qtyOk(ln.qty))
  const submit = () =>
    post.mutate(
      {
        outlet_id: outletId,
        business_date: date,
        reason_code: reason,
        lines: toLines(lines),
        confirm_negative: false,
      },
      { onSuccess: () => setLines([]) },
    )

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectInput
            label={t('inventory.docs.reason')}
            value={reason}
            onChange={(e) => setReason(e.target.value as Reason)}
          >
            {WASTE_REASONS.map((r) => (
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
        <ItemQtyLines lines={lines} units={units.data ?? []} onChange={setLines} />
        <div>
          <Button onClick={submit} disabled={invalid || post.isPending} aria-busy={post.isPending}>
            {t('inventory.docs.postWaste')}
          </Button>
        </div>
        {post.error ? <Alert>{errorMessage(post.error, t)}</Alert> : null}
      </Card>
      {undo.error ? <Alert>{errorMessage(undo.error, t)}</Alert> : null}
      <DocList
        docs={docs.data ?? []}
        actions={(d) =>
          canReverse &&
          d.status === 'posted' && (
            <Button variant="ghost" onClick={() => undo.mutate(d.id)} disabled={undo.isPending}>
              {t('inventory.opening.undo')}
            </Button>
          )
        }
      />
    </div>
  )
}
