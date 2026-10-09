import { useTranslation } from 'react-i18next'

import { CheckInput, SelectInput, TextInput } from '../../components/form'
import { useCategories, useUnits } from './api'
import type { DraftProblem, ItemDraft } from './itemDraft'
import { ITEM_TYPES, STORAGE_TYPES } from './labels'

const TRACKING_MODES = ['exact', 'estimated', 'untracked'] as const

export interface FieldsProps {
  d: ItemDraft
  set: (patch: Partial<ItemDraft>) => void
  issues: DraftProblem[]
  isNew: boolean
}

/** Names, SKU, type and category. */
export function IdentityFields({ d, set, issues }: FieldsProps) {
  const { t } = useTranslation()
  const categories = useCategories()
  return (
    <>
      <TextInput
        label={t('catalog.item.nameEn')}
        value={d.names.en}
        maxLength={200}
        onChange={(e) => set({ names: { ...d.names, en: e.target.value } })}
      />
      <TextInput
        label={t('catalog.item.nameId')}
        value={d.names.id}
        maxLength={200}
        onChange={(e) => set({ names: { ...d.names, id: e.target.value } })}
      />
      <TextInput
        label={t('catalog.item.sku')}
        value={d.sku}
        maxLength={64}
        invalid={issues.includes('sku')}
        onChange={(e) => set({ sku: e.target.value })}
      />
      <SelectInput
        label={t('catalog.items.type')}
        value={d.type}
        onChange={(e) => set({ type: e.target.value as ItemDraft['type'] })}
      >
        {ITEM_TYPES.map((k) => (
          <option key={k} value={k}>
            {t(`catalog.types.${k}`)}
          </option>
        ))}
      </SelectInput>
      <SelectInput
        label={t('catalog.item.category')}
        value={d.category_id}
        onChange={(e) => set({ category_id: e.target.value })}
      >
        <option value="">{t('catalog.item.noCategory')}</option>
        {categories.data?.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </SelectInput>
    </>
  )
}

/** Base unit, storage, shelf life, allergens and flags. */
export function StockFields({ d, set, issues, isNew }: FieldsProps) {
  const { t } = useTranslation()
  const units = useUnits()
  return (
    <>
      <SelectInput
        label={t('catalog.item.baseUnit')}
        value={d.base_unit_id}
        // The server refuses a new base unit: it would rescale every recorded quantity.
        disabled={!isNew}
        onChange={(e) => set({ base_unit_id: e.target.value })}
      >
        <option value="">{t('catalog.item.chooseUnit')}</option>
        {units.data?.map((u) => (
          <option key={u.id} value={u.id}>
            {`${u.code} (${u.name})`}
          </option>
        ))}
      </SelectInput>
      <SelectInput
        label={t('catalog.item.storage')}
        value={d.storage_type}
        onChange={(e) => set({ storage_type: e.target.value as ItemDraft['storage_type'] })}
      >
        <option value="">{t('catalog.item.noStorage')}</option>
        {STORAGE_TYPES.map((k) => (
          <option key={k} value={k}>
            {t(`catalog.storage.${k}`)}
          </option>
        ))}
      </SelectInput>
      <TextInput
        label={t('catalog.item.shelfLife')}
        inputMode="numeric"
        value={d.shelf_life}
        invalid={issues.includes('shelfLife')}
        onChange={(e) => set({ shelf_life: e.target.value })}
      />
      <TextInput
        label={t('catalog.item.allergens')}
        value={d.allergens}
        onChange={(e) => set({ allergens: e.target.value })}
      />
      <SelectInput
        label={t('catalog.item.tracking')}
        value={d.tracking_mode}
        onChange={(e) => set({ tracking_mode: e.target.value as ItemDraft['tracking_mode'] })}
      >
        {TRACKING_MODES.map((k) => (
          <option key={k} value={k}>
            {t(`catalog.tracking.${k}`)}
          </option>
        ))}
      </SelectInput>
      <p className="text-sm text-muted sm:col-span-2">
        {t(`catalog.tracking.${d.tracking_mode}Help`)}
      </p>
      <TextInput
        label={t('catalog.item.standardCost')}
        inputMode="decimal"
        value={d.standard_cost}
        invalid={issues.includes('standardCost')}
        onChange={(e) => set({ standard_cost: e.target.value })}
      />
      {d.type === 'menu' && (
        <TextInput
          label={t('catalog.item.targetPct')}
          inputMode="decimal"
          value={d.target_pct}
          invalid={issues.includes('targetPct')}
          onChange={(e) => set({ target_pct: e.target.value })}
        />
      )}
      {!isNew && (
        <CheckInput
          label={t('catalog.item.active')}
          checked={d.is_active}
          onChange={(v) => set({ is_active: v })}
        />
      )}
    </>
  )
}
