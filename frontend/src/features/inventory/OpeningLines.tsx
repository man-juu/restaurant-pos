import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { UnitOut } from '../../lib/api/types'
import type { OpeningLineDraft } from './openingDraft'

export function OpeningLines({
  lines,
  units,
  currency,
  onChange,
}: {
  lines: OpeningLineDraft[]
  units: UnitOut[]
  currency: string
  onChange: (lines: OpeningLineDraft[]) => void
}) {
  const { t } = useTranslation()
  const update = (i: number, patch: Partial<OpeningLineDraft>) =>
    onChange(lines.map((ln, j) => (j === i ? { ...ln, ...patch } : ln)))

  return (
    <ul className="flex flex-col gap-3">
      {lines.map((ln, i) => (
        <li
          key={ln.item_id}
          className="grid items-end gap-3 rounded-xl border border-line p-3 sm:grid-cols-3 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr_1fr_auto]"
        >
          <p className="self-center font-semibold sm:col-span-3 lg:col-span-1">{ln.label}</p>
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
            {units.map((u) => (
              <option key={u.id} value={u.id}>
                {u.code}
              </option>
            ))}
          </SelectInput>
          <TextInput
            label={t('inventory.opening.cost', { currency })}
            inputMode="decimal"
            value={ln.cost}
            onChange={(e) => update(i, { cost: e.target.value })}
          />
          <TextInput
            label={t('inventory.opening.lot')}
            maxLength={64}
            value={ln.lot}
            onChange={(e) => update(i, { lot: e.target.value })}
          />
          <TextInput
            label={t('inventory.opening.expiry')}
            type="date"
            value={ln.expiry}
            onChange={(e) => update(i, { expiry: e.target.value })}
          />
          <Button variant="ghost" onClick={() => onChange(lines.filter((_, j) => j !== i))}>
            {t('settings.remove')}
          </Button>
        </li>
      ))}
    </ul>
  )
}
