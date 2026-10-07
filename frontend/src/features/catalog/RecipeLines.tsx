import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { UnitOut } from '../../lib/api/types'
import type { LineDraft } from './recipeDraft'

/** Editable recipe lines: quantity, unit and preparation waste per component. */
export function RecipeLines({
  lines,
  units,
  onChange,
}: {
  lines: LineDraft[]
  units: UnitOut[]
  onChange: (lines: LineDraft[]) => void
}) {
  const { t } = useTranslation()
  const update = (i: number, patch: Partial<LineDraft>) =>
    onChange(lines.map((ln, j) => (j === i ? { ...ln, ...patch } : ln)))

  return (
    <ul className="flex flex-col gap-3">
      {lines.map((ln, i) => (
        <li
          key={ln.component_item_id}
          className="grid items-end gap-3 rounded-xl border border-line p-3 sm:grid-cols-[2fr_1fr_1fr_1fr_auto]"
        >
          <p className="self-center font-semibold">{ln.label}</p>
          <TextInput
            label={t('catalog.recipe.qty')}
            inputMode="decimal"
            value={ln.qty}
            onChange={(e) => update(i, { qty: e.target.value })}
          />
          <SelectInput
            label={t('catalog.conversions.unit')}
            value={ln.unit_id}
            onChange={(e) => update(i, { unit_id: e.target.value })}
          >
            <option value="">{t('catalog.item.chooseUnit')}</option>
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.code}
              </option>
            ))}
          </SelectInput>
          <TextInput
            label={t('catalog.recipe.waste')}
            inputMode="decimal"
            value={ln.waste}
            onChange={(e) => update(i, { waste: e.target.value })}
          />
          <Button variant="ghost" onClick={() => onChange(lines.filter((_, j) => j !== i))}>
            {t('settings.remove')}
          </Button>
        </li>
      ))}
    </ul>
  )
}
