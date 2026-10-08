import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { UnitOut } from '../../lib/api/types'
import type { QuickLineDraft } from './quickDraft'

export function QuickLines({
  lines,
  units,
  currency,
  onChange,
}: {
  lines: QuickLineDraft[]
  units: UnitOut[]
  currency: string
  onChange: (lines: QuickLineDraft[]) => void
}) {
  const { t } = useTranslation()
  const update = (i: number, patch: Partial<QuickLineDraft>) =>
    onChange(lines.map((ln, j) => (j === i ? { ...ln, ...patch } : ln)))
  return (
    <ul className="flex flex-col gap-3">
      {lines.map((ln, i) => (
        <li
          key={ln.item_id}
          className="grid items-end gap-3 rounded-xl border border-line p-3 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr_auto]"
        >
          <p className="self-center font-semibold sm:col-span-2 lg:col-span-1">{ln.label}</p>
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
            label={t('purchasing.quick.paid', { currency })}
            inputMode="numeric"
            value={ln.total}
            onChange={(e) => update(i, { total: e.target.value })}
          />
          <TextInput
            label={t('purchasing.quick.expiry')}
            type="date"
            value={ln.expiry}
            onChange={(e) => update(i, { expiry: e.target.value })}
          />
          <Button variant="ghost" onClick={() => onChange(lines.filter((_, j) => j !== i))}>
            {t('purchasing.quick.remove')}
          </Button>
        </li>
      ))}
    </ul>
  )
}
