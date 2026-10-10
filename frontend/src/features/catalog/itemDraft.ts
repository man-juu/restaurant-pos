/** Item form state <-> API body, and validation that mirrors the server rules (FR-CAT-001). */
import type { ItemIn, ItemOut } from '../../lib/api/types'
import { bpToPercent, optionalPercentOk, percentToBp } from '../../lib/percent'

export interface ConversionDraft {
  unit_id: string
  factor: string
}

export interface ItemDraft {
  sku: string
  barcode: string
  type: ItemIn['type']
  category_id: string
  base_unit_id: string
  tracking_mode: 'exact' | 'estimated' | 'untracked'
  standard_cost: string
  target_pct: string
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
  barcode: '',
  type: 'menu',
  category_id: '',
  base_unit_id: '',
  tracking_mode: 'exact',
  standard_cost: '',
  target_pct: '',
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
    barcode: item.barcode ?? '',
    type: item.type,
    category_id: item.category_id ?? '',
    base_unit_id: item.base_unit_id,
    tracking_mode: (item.tracking_mode ?? 'exact') as ItemDraft['tracking_mode'],
    standard_cost: item.standard_cost == null ? '' : String(item.standard_cost),
    target_pct: item.target_food_cost_bp == null ? '' : bpToPercent(item.target_food_cost_bp, 'en'),
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

export type DraftProblem =
  'sku' | 'barcode' | 'name' | 'unit' | 'shelfLife' | 'conversion' | 'standardCost' | 'targetPct'

const SHELF = /^\d{1,5}$/

/** Each rule is a check and the problem it reports; a table instead of an if-chain. */
const RULES: [DraftProblem, (d: ItemDraft) => boolean][] = [
  ['sku', (d) => !SKU.test(d.sku.trim())],
  ['barcode', (d) => Boolean(d.barcode.trim()) && !SKU.test(d.barcode.trim())],
  ['name', (d) => !d.names.en.trim() && !d.names.id.trim()],
  ['unit', (d) => !d.base_unit_id],
  ['shelfLife', (d) => Boolean(d.shelf_life) && !(SHELF.test(d.shelf_life) && +d.shelf_life >= 1)],
  ['standardCost', (d) => Boolean(d.standard_cost) && !FACTOR.test(d.standard_cost)],
  ['targetPct', (d) => !optionalPercentOk(d.target_pct)],
  ['conversion', (d) => conversionsInvalid(d)],
]

export function problems(d: ItemDraft): DraftProblem[] {
  return RULES.filter(([, failed]) => failed(d)).map(([problem]) => problem)
}

function conversionsInvalid(d: ItemDraft): boolean {
  const units = d.conversions.map((c) => c.unit_id)
  const bad = d.conversions.some(
    (c) =>
      !c.unit_id ||
      c.unit_id === d.base_unit_id ||
      !FACTOR.test(c.factor) ||
      !+c.factor.replace(',', '.'),
  )
  return bad || new Set(units).size !== units.length
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
    barcode: d.barcode.trim() || null,
    type: d.type,
    category_id: d.category_id || null,
    base_unit_id: d.base_unit_id,
    is_stocked: d.tracking_mode !== 'untracked',
    tracking_mode: d.tracking_mode,
    // Exact decimal string (per base unit), never a float.
    standard_cost: d.standard_cost ? d.standard_cost.replace(',', '.') : null,
    target_food_cost_bp: d.target_pct.trim() ? percentToBp(d.target_pct) : null,
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
