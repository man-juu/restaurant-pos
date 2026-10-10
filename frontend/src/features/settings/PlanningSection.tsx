import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

type Props = { data: AllSettings; canEdit: boolean }
type Planning = NonNullable<AllSettings['planning']>
type Field = keyof Planning

/** A typed 0 stays 0; an empty box falls back to the default. */
const toInt = (text: string, fallback: number) => {
  const digits = text.replace(/\D/g, '')
  return digits ? Number.parseInt(digits, 10) : fallback
}

/** Field and its default; the server checks the allowed range. */
const FIELDS: [Field, number][] = [
  ['forecast_weeks', 8],
  ['forecast_min_days', 28],
  ['order_cost', 0],
  ['holding_cost_pct', 25],
  ['plan_days', 3],
  ['reliability_weight_pct', 30],
  ['lead_day_cost_bp', 0],
]

/** FR-INV-018, FR-PRD-005, FR-PUR-007: how forecasts, order quantities, the production plan
 *  and vendor suggestions are worked out. */
export function PlanningSection({ data, canEdit }: Props) {
  const { t } = useTranslation()
  const save = useSaveSetting('planning')
  const [v, setV] = useState<Record<string, string>>(() =>
    Object.fromEntries(FIELDS.map(([k, d]) => [k, String(data.planning?.[k] ?? d)])),
  )
  const body = Object.fromEntries(FIELDS.map(([k, d]) => [k, toInt(v[k], d)])) as Planning
  return (
    <Card className="flex flex-col gap-3">
      <fieldset disabled={!canEdit} className="grid gap-3 sm:grid-cols-2">
        {FIELDS.map(([k]) => (
          <TextInput
            key={k}
            label={t(`settings.planning.${k}`)}
            inputMode="numeric"
            value={v[k]}
            onChange={(e) => setV({ ...v, [k]: e.target.value })}
          />
        ))}
      </fieldset>
      <p className="text-sm text-muted">{t('settings.planning.help')}</p>
      {canEdit && <SaveBar mutation={save} onSave={() => save.mutate(body)} />}
    </Card>
  )
}
