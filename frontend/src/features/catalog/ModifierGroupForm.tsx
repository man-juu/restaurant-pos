import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, TextInput } from '../../components/form'
import { Button, Card } from '../../components/ui'
import type { ModifierGroupIn, ModifierGroupOut, ModifierOptionIn } from '../../lib/api/types'
import { SaveBar } from '../settings/shared'
import { optionValid } from './modifierDraft'
import { ModifierOptionRow } from './ModifierOptionRow'
import { useSaveModifierGroup } from './modifierApi'

const NEW_OPTION: ModifierOptionIn = { name: '', price_delta: 0, is_active: true }

/** Only the writable fields: the API refuses unknown ones. */
function toGroupIn(g?: ModifierGroupOut): ModifierGroupIn {
  if (!g) return { name: '', min_select: 0, max_select: 1, is_active: true, options: [NEW_OPTION] }
  const { name, min_select, max_select, is_active, options } = g
  return { name, min_select, max_select, is_active, options }
}

const count = (v: string) => Math.max(0, Math.min(20, Number.parseInt(v, 10) || 0))

export function ModifierGroupForm({
  group,
  onDone,
}: {
  group?: ModifierGroupOut
  onDone: () => void
}) {
  const { t } = useTranslation()
  const save = useSaveModifierGroup()
  const [d, setD] = useState(() => toGroupIn(group))
  const set = (patch: Partial<ModifierGroupIn>) => setD((old) => ({ ...old, ...patch }))
  const setOption = (i: number, o: ModifierOptionIn) =>
    set({ options: d.options.map((old, j) => (j === i ? o : old)) })
  const min = d.min_select ?? 0
  const max = d.max_select ?? 1
  const valid =
    d.name.trim() !== '' &&
    min <= max &&
    max >= 1 &&
    d.options.length > 0 &&
    d.options.every(optionValid)

  return (
    <Card className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-3 sm:items-end">
        <TextInput
          label={t('catalog.modifiers.name')}
          value={d.name}
          maxLength={120}
          onChange={(e) => set({ name: e.target.value })}
        />
        <TextInput
          label={t('catalog.modifiers.min')}
          inputMode="numeric"
          value={String(min)}
          onChange={(e) => set({ min_select: count(e.target.value) })}
        />
        <TextInput
          label={t('catalog.modifiers.max')}
          inputMode="numeric"
          value={String(max)}
          invalid={min > max || max < 1}
          onChange={(e) => set({ max_select: count(e.target.value) })}
        />
      </div>
      <p className="text-sm text-ink-soft">{t('catalog.modifiers.selectHelp')}</p>
      <ul className="flex flex-col gap-3">
        {d.options.map((o, i) => (
          <ModifierOptionRow
            key={o.id ?? `new-${i}`}
            option={o}
            onChange={(v) => setOption(i, v)}
          />
        ))}
      </ul>
      <div>
        <Button variant="ghost" onClick={() => set({ options: [...d.options, NEW_OPTION] })}>
          {t('catalog.modifiers.addOption')}
        </Button>
      </div>
      <CheckInput
        label={t('catalog.item.active')}
        checked={d.is_active ?? true}
        onChange={(v) => set({ is_active: v })}
      />
      <div className="flex flex-wrap gap-3">
        <SaveBar
          mutation={save}
          disabled={!valid}
          onSave={() =>
            save.mutate(
              { id: group?.id, body: { ...d, name: d.name.trim() } },
              { onSuccess: onDone },
            )
          }
        />
        <Button variant="ghost" onClick={onDone}>
          {t('catalog.cancel')}
        </Button>
      </div>
    </Card>
  )
}
