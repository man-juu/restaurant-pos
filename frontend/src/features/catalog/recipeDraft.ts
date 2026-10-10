/** Recipe form state <-> API body (FR-CAT-005). Quantities stay strings: exact decimals. */
import type { BomIn, BomOut } from '../../lib/api/types'

export interface LineDraft {
  component_item_id: string
  label: string
  qty: string
  unit_id: string
  waste: string
}

export interface RecipeDraft {
  lines: LineDraft[]
  yield_qty: string
  yield_unit_id: string
}

export type RecipeProblem = 'lines' | 'qty' | 'waste' | 'yield'

const QTY = /^\d{1,14}([.,]\d{1,4})?$/
const WASTE = /^\d{1,2}([.,]\d{1,2})?$/ // 0 to 99.99 %
const positive = (text: string) => QTY.test(text) && Number(text.replace(',', '.')) > 0
const dot = (text: string) => text.replace(',', '.')

export function fromBom(bom?: BomOut): RecipeDraft {
  return {
    lines: (bom?.lines ?? []).map((ln) => ({
      component_item_id: ln.component_item_id,
      label: `${ln.component_name} (${ln.component_sku})`,
      qty: ln.qty,
      unit_id: ln.unit_id,
      waste: ln.waste_pct,
    })),
    yield_qty: bom?.yield_qty ?? '',
    yield_unit_id: bom?.yield_unit_id ?? '',
  }
}

export function recipeProblems(d: RecipeDraft, needsYield: boolean): RecipeProblem[] {
  const found: RecipeProblem[] = []
  if (d.lines.length === 0) found.push('lines')
  if (d.lines.some((ln) => !positive(ln.qty) || !ln.unit_id)) found.push('qty')
  if (d.lines.some((ln) => ln.waste !== '' && !WASTE.test(ln.waste))) found.push('waste')
  if (needsYield && !(positive(d.yield_qty) && d.yield_unit_id)) found.push('yield')
  return found
}

export function toBomBody(d: RecipeDraft, needsYield: boolean): BomIn {
  return {
    lines: d.lines.map((ln) => ({
      component_item_id: ln.component_item_id,
      qty: dot(ln.qty),
      unit_id: ln.unit_id,
      waste_pct: dot(ln.waste || '0'),
    })),
    // Menu items make one base unit; semi-finished items say how much one batch makes.
    ...(needsYield ? { yield_qty: dot(d.yield_qty), yield_unit_id: d.yield_unit_id } : {}),
  }
}
