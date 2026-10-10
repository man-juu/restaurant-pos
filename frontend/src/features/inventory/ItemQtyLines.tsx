import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { UnitOut } from '../../lib/api/types'
import { ComponentPicker } from '../catalog/ComponentPicker'
import { newQtyLine, qtyOk, type QtyLineDraft } from './qtyLines'

const STOCK_TYPES = ['ingredient', 'semi_finished', 'menu'] as const

/** Item + quantity + unit rows with an item search below them (waste, adjustments). */
export function ItemQtyLines({
  lines,
  units,
  signed = false,
  onChange,
}: {
  lines: QtyLineDraft[]
  units: UnitOut[]
  signed?: boolean
  onChange: (lines: QtyLineDraft[]) => void
}) {
  const { t } = useTranslation()
  const update = (i: number, patch: Partial<QtyLineDraft>) =>
    onChange(lines.map((ln, j) => (j === i ? { ...ln, ...patch } : ln)))

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-3">
        {lines.map((ln, i) => (
          <li
            key={ln.item_id}
            className="grid items-end gap-3 rounded-xl border border-line p-3 sm:grid-cols-[2fr_1fr_1fr_auto]"
          >
            <p className="self-center font-semibold">{ln.label}</p>
            <TextInput
              label={t(signed ? 'inventory.docs.signedQty' : 'catalog.recipe.qty')}
              inputMode="decimal"
              value={ln.qty}
              invalid={ln.qty !== '' && !qtyOk(ln.qty, signed)}
              onChange={(e) => update(i, { qty: e.target.value })}
            />
            <SelectInput
              label={t('catalog.conversions.unit')}
              value={ln.unit_id}
              onChange={(e) => update(i, { unit_id: e.target.value })}
            >
              {units.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.code}
                </option>
              ))}
            </SelectInput>
            <Button variant="ghost" onClick={() => onChange(lines.filter((_, j) => j !== i))}>
              {t('settings.remove')}
            </Button>
          </li>
        ))}
      </ul>
      <ComponentPicker
        label={t('inventory.opening.add')}
        types={STOCK_TYPES}
        exclude={new Set(lines.map((ln) => ln.item_id))}
        onPick={(item) => onChange([...lines, newQtyLine(item)])}
      />
    </div>
  )
}
