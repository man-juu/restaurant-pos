import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { ItemSummary } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { ComponentPicker } from '../catalog/ComponentPicker'
import { useLevels, useSaveLevels } from './levelApi'
import { FIELDS, fromLevel, invalid, type LevelDraft, toBody } from './levelDraft'

/** docs/05 2.3: par level (daily prep list) and min / reorder point / max per item. */
export function LevelsTab({ outletId, canManage }: { outletId: string; canManage: boolean }) {
  const { t, i18n } = useTranslation()
  const levels = useLevels(outletId, i18n.language)
  const save = useSaveLevels()
  const [edits, setEdits] = useState<LevelDraft[]>()
  const drafts = edits ?? levels.data?.map(fromLevel) ?? []
  const change = (i: number, d: LevelDraft) => setEdits(drafts.map((x, j) => (j === i ? d : x)))
  const add = (item: ItemSummary) =>
    setEdits([
      ...drafts,
      {
        item_id: item.id,
        label: item.name,
        unit: '',
        onHand: '',
        values: { par_qty: '', min_qty: '', reorder_point: '', max_qty: '' },
      },
    ])
  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('inventory.levels.help')}</p>
      {levels.error && <Alert>{errorMessage(levels.error, t)}</Alert>}
      <ul className="flex flex-col gap-3">
        {drafts.map((d, i) => (
          <LevelRow
            key={d.item_id}
            draft={d}
            disabled={!canManage}
            onChange={(x) => change(i, x)}
          />
        ))}
      </ul>
      {canManage && (
        <>
          <ComponentPicker
            exclude={new Set(drafts.map((d) => d.item_id))}
            onPick={add}
            label={t('inventory.levels.add')}
          />
          {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
          <Button
            className="self-start"
            disabled={!edits || drafts.some(invalid) || save.isPending}
            onClick={() =>
              save.mutate(toBody(outletId, drafts), { onSuccess: () => setEdits(undefined) })
            }
          >
            {t('inventory.levels.save')}
          </Button>
        </>
      )}
    </Card>
  )
}

function LevelRow({
  draft,
  disabled,
  onChange,
}: {
  draft: LevelDraft
  disabled: boolean
  onChange: (d: LevelDraft) => void
}) {
  const { t } = useTranslation()
  return (
    <li className="grid items-end gap-3 rounded-xl border border-line p-3 sm:grid-cols-2 lg:grid-cols-[2fr_repeat(4,1fr)]">
      <p className="self-center font-semibold sm:col-span-2 lg:col-span-1">
        {draft.label}
        {draft.onHand && (
          <span className="block text-sm font-normal text-ink-soft">
            {t('inventory.levels.onHand', { qty: draft.onHand, unit: draft.unit })}
          </span>
        )}
      </p>
      {FIELDS.map((f) => (
        <TextInput
          key={f}
          label={t(`inventory.levels.${f}`)}
          inputMode="decimal"
          disabled={disabled}
          value={draft.values[f]}
          onChange={(e) => onChange({ ...draft, values: { ...draft.values, [f]: e.target.value } })}
        />
      ))}
    </li>
  )
}
