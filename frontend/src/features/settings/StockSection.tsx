import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

const KINDS = ['sale', 'production', 'transfer', 'other'] as const
const POLICIES = ['allow', 'warn', 'block'] as const
type Policy = (typeof POLICIES)[number]
type PolicySet = Record<(typeof KINDS)[number], Policy>

const withDefaults = (p: Partial<PolicySet> | undefined): PolicySet => ({
  sale: p?.sale ?? 'allow',
  production: p?.production ?? 'warn',
  transfer: p?.transfer ?? 'warn',
  other: p?.other ?? 'block',
})

/** FR-INV-006: what happens when more is used than the system shows on hand. */
export function StockSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('stock')
  const [policy, setPolicy] = useState(() => withDefaults(data.stock.negative_stock))
  const [days, setDays] = useState(String(data.stock.expiry_warning_days ?? 2))
  const [low, setLow] = useState(String(data.stock.low_days_alert ?? 2))
  const [variance, setVariance] = useState(String(data.stock.count_variance_alert ?? 0))
  const varianceOk = /^\d{1,12}$/.test(variance)
  const ok = (v: string) => /^\d{1,2}$/.test(v) && Number(v) <= 60
  const daysOk = ok(days) && ok(low) && varianceOk

  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('settings.stock.help')}</p>
      <fieldset disabled={!canEdit} className="grid gap-3 sm:grid-cols-2">
        {KINDS.map((kind) => (
          <SelectInput
            key={kind}
            label={t(`settings.stock.kinds.${kind}`)}
            value={policy[kind]}
            onChange={(e) => setPolicy({ ...policy, [kind]: e.target.value as Policy })}
          >
            {POLICIES.map((p) => (
              <option key={p} value={p}>
                {t(`settings.stock.policies.${p}`)}
              </option>
            ))}
          </SelectInput>
        ))}
        <TextInput
          label={t('settings.stock.expiryDays')}
          inputMode="numeric"
          value={days}
          invalid={!ok(days)}
          onChange={(e) => setDays(e.target.value)}
        />
        <TextInput
          label={t('settings.stock.lowDays')}
          inputMode="numeric"
          value={low}
          invalid={!ok(low)}
          onChange={(e) => setLow(e.target.value)}
        />
        <TextInput
          label={t('settings.stock.countVariance')}
          inputMode="numeric"
          value={variance}
          invalid={!varianceOk}
          onChange={(e) => setVariance(e.target.value)}
        />
      </fieldset>
      {canEdit && (
        <SaveBar
          mutation={save}
          onSave={() =>
            daysOk &&
            save.mutate({
              negative_stock: policy,
              expiry_warning_days: Number(days),
              low_days_alert: Number(low),
              count_variance_alert: Number(variance),
            })
          }
        />
      )}
    </Card>
  )
}
