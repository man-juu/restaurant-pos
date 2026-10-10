import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, TextInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { ModifierOptionIn } from '../../lib/api/types'
import { useItem } from './api'
import { ComponentPicker } from './ComponentPicker'
import { DELTA, MONEY } from './modifierDraft'

/** One option: name, price change and optional ingredient change ("extra egg", "no egg"). */
export function ModifierOptionRow({
  option,
  onChange,
}: {
  option: ModifierOptionIn
  onChange: (o: ModifierOptionIn) => void
}) {
  const { t } = useTranslation()
  const set = (patch: Partial<ModifierOptionIn>) => onChange({ ...option, ...patch })
  const [price, setPrice] = useState(String(option.price_delta ?? 0))
  return (
    <li className="grid gap-3 rounded-xl border border-line p-3 sm:grid-cols-2">
      <TextInput
        label={t('catalog.modifiers.option')}
        value={option.name}
        maxLength={120}
        onChange={(e) => set({ name: e.target.value })}
      />
      <TextInput
        label={t('catalog.modifiers.priceDelta')}
        inputMode="numeric"
        value={price}
        invalid={!MONEY.test(price)}
        onChange={(e) => {
          // An invalid entry becomes NaN, which optionValid rejects, so it cannot be saved.
          setPrice(e.target.value)
          set({ price_delta: MONEY.test(e.target.value) ? Number(e.target.value) : Number.NaN })
        }}
      />
      <IngredientChange option={option} set={set} />
      <CheckInput
        label={t('catalog.item.active')}
        checked={option.is_active ?? true}
        onChange={(v) => set({ is_active: v })}
      />
    </li>
  )
}

function IngredientChange({
  option,
  set,
}: {
  option: ModifierOptionIn
  set: (patch: Partial<ModifierOptionIn>) => void
}) {
  const { t, i18n } = useTranslation()
  const linked = useItem(option.ingredient_item_id ?? undefined, i18n.language)
  if (!option.ingredient_item_id)
    return (
      <div className="sm:col-span-2">
        <ComponentPicker
          exclude={new Set()}
          label={t('catalog.modifiers.ingredient')}
          onPick={(item) => set({ ingredient_item_id: item.id, ingredient_qty: '' })}
        />
      </div>
    )
  const qty = String(option.ingredient_qty ?? '')
  return (
    <div className="flex flex-wrap items-end gap-3 sm:col-span-2">
      <TextInput
        label={t('catalog.modifiers.ingredientQty', { name: linked.data?.name ?? '…' })}
        inputMode="decimal"
        value={qty}
        invalid={qty !== '' && !DELTA.test(qty)}
        onChange={(e) => set({ ingredient_qty: e.target.value })}
      />
      <Button
        variant="ghost"
        onClick={() => set({ ingredient_item_id: null, ingredient_qty: null })}
      >
        {t('catalog.modifiers.removeIngredient')}
      </Button>
    </div>
  )
}
