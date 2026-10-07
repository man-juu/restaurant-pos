import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { BomOut, ItemOut, ItemSummary, UnitOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { SaveBar } from '../settings/shared'
import { useUnits } from './api'
import { ComponentPicker } from './ComponentPicker'
import { todayIso } from './labels'
import { useRecipeMutations } from './recipeApi'
import { fromBom, type RecipeDraft, recipeProblems, toBomBody } from './recipeDraft'
import { RecipeLines } from './RecipeLines'

const newLine = (c: ItemSummary) => ({
  component_item_id: c.id,
  label: `${c.name} (${c.sku})`,
  qty: '',
  unit_id: c.base_unit_id,
  waste: '0',
})

/**
 * Edits a draft (`draft`), or starts a new one from `copyOf` (the current recipe). Saving
 * keeps it a draft; activating fixes it from a start date (FR-CAT-006).
 */
export function RecipeEditor({
  item,
  draft,
  copyOf,
  onClose,
}: {
  item: ItemOut
  draft?: BomOut
  copyOf?: BomOut
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const units = useUnits()
  const { save } = useRecipeMutations(item.id, i18n.language)
  const [d, setD] = useState<RecipeDraft>(() => fromBom(draft ?? copyOf))
  const needsYield = item.type === 'semi_finished'
  const issues = recipeProblems(d, needsYield)
  const set = (patch: Partial<RecipeDraft>) => setD((old) => ({ ...old, ...patch }))
  const body = toBomBody(d, needsYield)
  // Activation fixes what was saved, so unsaved edits must be saved first.
  const dirty =
    !draft || JSON.stringify(body) !== JSON.stringify(toBomBody(fromBom(draft), needsYield))
  const title = draft
    ? t('catalog.recipe.draft', { version: draft.version })
    : t('catalog.recipe.newVersion')

  return (
    <Card className="flex flex-col gap-4">
      <h3 className="font-display text-lg font-extrabold">{title}</h3>
      <RecipeLines lines={d.lines} units={units.data ?? []} onChange={(lines) => set({ lines })} />
      <ComponentPicker
        exclude={new Set([item.id, ...d.lines.map((ln) => ln.component_item_id)])}
        onPick={(c) => set({ lines: [...d.lines, newLine(c)] })}
      />
      {needsYield && <YieldFields d={d} set={set} units={units.data ?? []} />}
      {issues.length > 0 && (
        <p className="text-sm text-danger">
          {issues.map((p) => t(`catalog.recipe.problems.${p}`)).join(' ')}
        </p>
      )}
      <SaveBar
        mutation={save}
        disabled={issues.length > 0}
        onSave={() => save.mutate({ bomId: draft?.id, body })}
      />
      {draft ? (
        <ActivateBar item={item} draftId={draft.id} disabled={dirty} onDone={onClose} />
      ) : (
        <Button variant="ghost" onClick={onClose}>
          {t('catalog.cancel')}
        </Button>
      )}
    </Card>
  )
}

function YieldFields({
  d,
  set,
  units,
}: {
  d: RecipeDraft
  set: (patch: Partial<RecipeDraft>) => void
  units: UnitOut[]
}) {
  const { t } = useTranslation()
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <TextInput
        label={t('catalog.recipe.yield')}
        inputMode="decimal"
        value={d.yield_qty}
        onChange={(e) => set({ yield_qty: e.target.value })}
      />
      <SelectInput
        label={t('catalog.conversions.unit')}
        value={d.yield_unit_id}
        onChange={(e) => set({ yield_unit_id: e.target.value })}
      >
        <option value="">{t('catalog.item.chooseUnit')}</option>
        {units.map((u) => (
          <option key={u.id} value={u.id}>
            {u.code}
          </option>
        ))}
      </SelectInput>
    </div>
  )
}

function ActivateBar({
  item,
  draftId,
  disabled,
  onDone,
}: {
  item: ItemOut
  draftId: string
  disabled: boolean
  onDone: () => void
}) {
  const { t, i18n } = useTranslation()
  const { activate, remove } = useRecipeMutations(item.id, i18n.language)
  const [startDate, setStartDate] = useState(todayIso)
  const error = activate.error ?? remove.error
  return (
    <div className="flex flex-col gap-3 border-t border-line pt-4">
      <div className="grid items-end gap-3 sm:grid-cols-[1fr_auto_auto]">
        <TextInput
          label={t('catalog.recipe.startDate')}
          type="date"
          value={startDate}
          onChange={(e) => setStartDate(e.target.value)}
        />
        <Button
          onClick={() =>
            activate.mutate({ bomId: draftId, validFrom: startDate }, { onSuccess: onDone })
          }
          disabled={disabled || !startDate || activate.isPending}
          aria-busy={activate.isPending}
        >
          {t('catalog.recipe.activate')}
        </Button>
        <Button variant="ghost" onClick={() => remove.mutate(draftId, { onSuccess: onDone })}>
          {t('catalog.recipe.discard')}
        </Button>
      </div>
      {disabled && <p className="text-sm text-ink-soft">{t('catalog.recipe.saveFirst')}</p>}
      {error ? <Alert>{errorMessage(error, t)}</Alert> : null}
    </div>
  )
}
