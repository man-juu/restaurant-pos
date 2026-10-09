import { describe, expect, it } from 'vitest'

import type { CategoryOut, ItemOut } from '../../lib/api/types'
import { problems, toBody, toDraft } from './itemDraft'
import { fromBom, recipeProblems, toBomBody } from './recipeDraft'
import { treeOrder } from './tree'

const item: ItemOut = {
  id: 'i1',
  sku: 'NASI-01',
  type: 'menu',
  name: 'Fried rice',
  category_id: null,
  base_unit_id: 'pcs',
  is_active: true,
  is_stocked: false,
  tracking_mode: 'untracked',
  standard_cost: null,
  target_food_cost_bp: null,
  shelf_life_days: null,
  storage_type: null,
  allergens: ['egg'],
  version: 3,
  translations: [
    { language: 'en', name: 'Fried rice', description: null },
    { language: 'id', name: 'Nasi goreng', description: 'Pedas' },
    { language: 'ko', name: '볶음밥', description: null },
  ],
  conversions: [],
}

describe('item form (FR-CAT-001, 002, 009)', () => {
  it('round-trips an item and keeps translations the form does not show', () => {
    const body = toBody(toDraft(item), item)
    expect(body.translations).toEqual([
      { language: 'en', name: 'Fried rice', description: null },
      { language: 'id', name: 'Nasi goreng', description: 'Pedas' },
      { language: 'ko', name: '볶음밥', description: null },
    ])
    expect(body).toMatchObject({ sku: 'NASI-01', allergens: ['egg'], shelf_life_days: null })
  })

  it('flags what the server would refuse', () => {
    const draft = {
      ...toDraft(),
      sku: 'bad sku',
      shelf_life: '0',
      conversions: [{ unit_id: 'pcs', factor: '2' }],
      base_unit_id: 'pcs',
    }
    expect(problems(draft)).toEqual(['sku', 'name', 'shelfLife', 'conversion'])
  })

  it('sends conversion factors as exact decimal strings', () => {
    const draft = { ...toDraft(item), conversions: [{ unit_id: 'box', factor: '2500,5' }] }
    expect(problems(draft)).toEqual([])
    expect(toBody(draft, item).conversions).toEqual([{ unit_id: 'box', factor_to_base: '2500.5' }])
  })
})

describe('recipe form (FR-CAT-005)', () => {
  const line = { component_item_id: 'rice', label: 'Rice', qty: '200', unit_id: 'g', waste: '0' }

  it('needs lines, positive quantities, waste below 100 and a yield for semi-finished', () => {
    const empty = fromBom()
    expect(recipeProblems(empty, false)).toEqual(['lines'])
    const bad = { ...empty, lines: [{ ...line, qty: '0', waste: '100' }] }
    expect(recipeProblems(bad, true)).toEqual(['qty', 'waste', 'yield'])
  })

  it('sends exact decimals and a yield only when needed', () => {
    const d = { lines: [{ ...line, qty: '1,5', waste: '' }], yield_qty: '0,5', yield_unit_id: 'kg' }
    expect(toBomBody(d, false)).toEqual({
      lines: [{ component_item_id: 'rice', qty: '1.5', unit_id: 'g', waste_pct: '0' }],
    })
    expect(toBomBody(d, true)).toMatchObject({ yield_qty: '0.5', yield_unit_id: 'kg' })
  })
})

describe('category tree', () => {
  const cat = (id: string, parent: string | null): CategoryOut => ({
    id,
    name: id,
    parent_id: parent,
    sort_order: 0,
    is_active: true,
  })

  it('lists children under their parent with depth', () => {
    const rows = treeOrder([cat('beef', 'meat'), cat('meat', null), cat('drinks', null)])
    expect(rows.map((r) => `${r.depth}:${r.row.id}`)).toEqual(['0:meat', '1:beef', '0:drinks'])
  })
})
