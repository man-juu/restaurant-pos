import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { ItemSummary } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useUnits } from '../catalog/api'
import { ComponentPicker } from '../catalog/ComponentPicker'
import { todayIso } from '../catalog/labels'
import { usePostOpening, useReverseOpening } from './api'
import { OpeningImport } from './OpeningImport'
import { OpeningLines } from './OpeningLines'
import { lineProblem, type OpeningLineDraft, toOpeningBody } from './openingDraft'

const STOCK_TYPES = ['ingredient', 'semi_finished', 'menu'] as const

/** Stock on hand when an outlet starts using the system. Posted once per item; a mistake is
 * undone with "Undo", which posts a reversal (history is never deleted, FR-X-005). */
export function OpeningTab({ outletId, currency }: { outletId: string; currency: string }) {
  const { t } = useTranslation()
  const units = useUnits()
  const post = usePostOpening()
  const undo = useReverseOpening()
  const [date, setDate] = useState(todayIso)
  const [lines, setLines] = useState<OpeningLineDraft[]>([])
  const invalid = lines.length === 0 || lines.some((ln) => lineProblem(ln, currency))
  const add = (item: ItemSummary) =>
    setLines([
      ...lines,
      {
        item_id: item.id,
        label: `${item.name} (${item.sku})`,
        qty: '',
        unit_id: item.base_unit_id,
        cost: '',
        lot: '',
        expiry: '',
      },
    ])
  const submit = () =>
    post.mutate(toOpeningBody(outletId, date, lines, currency), { onSuccess: () => setLines([]) })

  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('inventory.opening.help')}</p>
      <TextInput
        label={t('inventory.opening.date')}
        type="date"
        value={date}
        className="max-w-xs"
        onChange={(e) => setDate(e.target.value)}
      />
      <OpeningImport businessDate={date} />
      <OpeningLines
        lines={lines}
        units={units.data ?? []}
        currency={currency}
        onChange={setLines}
      />
      <ComponentPicker
        label={t('inventory.opening.add')}
        types={STOCK_TYPES}
        exclude={new Set(lines.map((ln) => ln.item_id))}
        onPick={add}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={submit} disabled={invalid || post.isPending} aria-busy={post.isPending}>
          {t('inventory.opening.post')}
        </Button>
        {post.isSuccess && !undo.isSuccess && (
          <>
            <span role="status" className="text-sm text-good">
              {t('inventory.opening.posted', { count: post.data.movements })}
            </span>
            <Button variant="ghost" onClick={() => undo.mutate(post.data.doc_id)}>
              {t('inventory.opening.undo')}
            </Button>
          </>
        )}
        {undo.isSuccess && (
          <span role="status" className="text-sm text-good">
            {t('inventory.opening.undone')}
          </span>
        )}
      </div>
      {post.error || undo.error ? <Alert>{errorMessage(post.error ?? undo.error, t)}</Alert> : null}
    </Card>
  )
}
