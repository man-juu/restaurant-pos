import type { LevelOut, LevelsIn } from '../../lib/api/types'

export const FIELDS = ['par_qty', 'min_qty', 'reorder_point', 'max_qty'] as const
export type Field = (typeof FIELDS)[number]

export interface LevelDraft {
  item_id: string
  label: string
  unit: string
  onHand: string
  values: Record<Field, string>
}

const QTY = /^\d{1,14}([.,]\d{1,4})?$/

export const fromLevel = (lv: LevelOut): LevelDraft => ({
  item_id: lv.item_id,
  label: lv.name,
  unit: lv.unit_code,
  onHand: String(Number(lv.on_hand)),
  values: Object.fromEntries(
    FIELDS.map((f) => [f, lv[f] == null ? '' : String(Number(lv[f]))]),
  ) as Record<Field, string>,
})

export const invalid = (d: LevelDraft) =>
  FIELDS.some((f) => d.values[f] !== '' && !QTY.test(d.values[f]))

export function toBody(outletId: string, drafts: LevelDraft[]): LevelsIn {
  return {
    outlet_id: outletId,
    levels: drafts.map((d) => ({
      item_id: d.item_id,
      ...Object.fromEntries(
        FIELDS.map((f) => [f, d.values[f] === '' ? null : d.values[f].replace(',', '.')]),
      ),
    })),
  }
}
