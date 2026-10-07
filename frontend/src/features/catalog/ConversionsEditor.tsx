import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { UnitOut } from '../../lib/api/types'
import type { ConversionDraft } from './itemDraft'

/** FR-CAT-002: "1 box = 2500 g". Platform units (kg -> g) convert without a row. */
export function ConversionsEditor({
  rows,
  units,
  disabled,
  invalid,
  onChange,
}: {
  rows: ConversionDraft[]
  units: UnitOut[]
  disabled: boolean
  invalid: boolean
  onChange: (rows: ConversionDraft[]) => void
}) {
  const { t } = useTranslation()
  const update = (i: number, patch: Partial<ConversionDraft>) =>
    onChange(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  return (
    <fieldset disabled={disabled} className="flex flex-col gap-3">
      <legend className="pb-2 font-bold">{t('catalog.conversions.title')}</legend>
      <p className="text-sm text-ink-soft">{t('catalog.conversions.help')}</p>
      {rows.map((row, i) => (
        <div key={i} className="grid items-end gap-3 sm:grid-cols-[1fr_1fr_auto]">
          <SelectInput
            label={t('catalog.conversions.unit')}
            value={row.unit_id}
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
            label={t('catalog.conversions.factor')}
            inputMode="decimal"
            value={row.factor}
            invalid={invalid}
            onChange={(e) => update(i, { factor: e.target.value })}
          />
          <Button variant="ghost" onClick={() => onChange(rows.filter((_, j) => j !== i))}>
            {t('settings.remove')}
          </Button>
        </div>
      ))}
      <div>
        <Button
          variant="ghost"
          disabled={rows.length >= 20}
          onClick={() => onChange([...rows, { unit_id: '', factor: '' }])}
        >
          {t('catalog.conversions.add')}
        </Button>
      </div>
    </fieldset>
  )
}
