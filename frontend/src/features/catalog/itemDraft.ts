/** Item form state <-> API body, and validation that mirrors the server rules (FR-CAT-001). */
import type { ItemIn, ItemOut } from '../../lib/api/types'

export interface ConversionDraft {
  unit_id: string
  factor: string
}

export interface ItemDraft {
  sku: string
  type: ItemIn['type']
  category_id: string
  base_unit_id: string
  is_stocked: boolean
  shelf_life: string
  storage_type: '' | NonNullable<ItemIn['storage_type']>
  allergens: string
  names: { en: string; id: string }
  conversions: ConversionDraft[]
  is_active: boolean
}

const FORM_LANGUAGES = ['en', 'id'] as const
const SKU = /^[A-Za-z0-9._/-]{1,64}$/
const FACTOR = /^\d{1,12}([.,]\d{1,6})?$/

export const EMPTY_DRAFT: ItemDraft = {
  sku: '',
  type: 'menu',
  category_id: '',
  base_unit_id: '',
  is_stocked: true,
  shelf_life: '',
  storage_type: '',
  allergens: '',
  names: { en: '', id: '' },
  conversions: [],
  is_active: true,
}

export function toDraft(item?: ItemOut): ItemDraft {
  if (!item) return EMPTY_DRAFT
  const name = (lang: string) => item.translations.find((t) => t.language === lang)?.name ?? ''
  return {
    sku: item.sku,
    type: item.type,
    category_id: item.category_id ?? '',
    base_unit_id: item.base_unit_id,
    is_stocked: item.is_stocked,
    shelf_life: String(item.shelf_life_days ?? ''),
    storage_type: (item.storage_type ?? '') as ItemDraft['storage_type'],
    allergens: item.allergens.join(', '),
    names: { en: name('en'), id: name('id') },
    conversions: item.conversions.map((c) => ({
      unit_id: c.unit_id,
      factor: String(c.factor_to_base),
    })),
    is_active: item.is_active,
  }
}

export type DraftProblem = 'sku' | 'name' | 'unit' | 'shelfLife' | 'conversion'

export function problems(d: ItemDraft): DraftProblem[] {
  const found: DraftProblem[] = []
  if (!SKU.test(d.sku.trim())) found.push('sku')
  if (!d.names.en.trim() && !d.names.id.trim()) found.push('name')
  if (!d.base_unit_id) found.push('unit')
  if (d.shelf_life && !(/^\d{1,5}$/.test(d.shelf_life) && +d.shelf_life >= 1))
    found.push('shelfLife')
  const units = d.conversions.map((c) => c.unit_id)
  const badConversion = d.conversions.some(
    (c) =>
      !c.unit_id ||
      c.unit_id === d.base_unit_id ||
      !FACTOR.test(c.factor) ||
      !+c.factor.replace(',', '.'),
  )
  if (badConversion || new Set(units).size !== units.length) found.push('conversion')
  return found
}

/** Translations in other languages (added later through import or the API) are kept. */
export function toBody(d: ItemDraft, item?: ItemOut): ItemIn {
  const others = (item?.translations ?? []).filter(
    (t) => !(FORM_LANGUAGES as readonly string[]).includes(t.language),
  )
  const typed = FORM_LANGUAGES.filter((lang) => d.names[lang].trim()).map((lang) => ({
    language: lang,
    name: d.names[lang].trim(),
    description: item?.translations.find((t) => t.language === lang)?.description ?? null,
  }))
  return {
    sku: d.sku.trim(),
    type: d.type,
    category_id: d.category_id || null,
    base_unit_id: d.base_unit_id,
    is_stocked: d.is_stocked,
    shelf_life_days: d.shelf_life ? Number(d.shelf_life) : null,
    storage_type: d.storage_type || null,
    allergens: d.allergens
      .split(',')
      .map((a) => a.trim())
      .filter(Boolean),
    translations: [...typed, ...others],
    // Factors stay strings: exact decimals, never floats.
    conversions: d.conversions.map((c) => ({
      unit_id: c.unit_id,
      factor_to_base: c.factor.replace(',', '.'),
    })),
  }
}
