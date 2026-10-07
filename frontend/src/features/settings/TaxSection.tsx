import { clsx } from 'clsx'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { bpToPercent, percentToBp } from '../../lib/percent'
import { useSaveSetting } from './api'
import { SaveBar, inputClass } from './shared'

export function TaxSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t, i18n } = useTranslation()
  const save = useSaveSetting('tax')
  const [rules, setRules] = useState(() =>
    (data.tax.rules ?? []).map((r) => ({ ...r, rateText: bpToPercent(r.rate_bp, i18n.language) })),
  )
  const invalid = rules.some((r) => percentToBp(r.rateText) === null || !r.name.trim())
  const update = (i: number, patch: Partial<(typeof rules)[number]>) =>
    setRules((all) => all.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('settings.tax.help')}</p>
      {rules.map((rule, i) => (
        <fieldset
          key={rule.id}
          disabled={!canEdit}
          className="grid gap-3 rounded-xl border border-line p-3 sm:grid-cols-2 lg:grid-cols-5"
        >
          <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
            {t('settings.tax.name')}
            <input
              className={inputClass}
              value={rule.name}
              onChange={(e) => update(i, { name: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
            {t('settings.tax.rate')}
            <input
              className={clsx(inputClass, percentToBp(rule.rateText) === null && 'border-danger')}
              inputMode="decimal"
              value={rule.rateText}
              aria-invalid={percentToBp(rule.rateText) === null}
              onChange={(e) => update(i, { rateText: e.target.value })}
            />
          </label>
          {(['price_includes_tax', 'applies_to_service_charge', 'active'] as const).map((flag) => (
            <label key={flag} className="flex min-h-11 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-5 w-5 accent-[var(--accent)]"
                checked={Boolean(rule[flag])}
                onChange={(e) => update(i, { [flag]: e.target.checked })}
              />
              {t(
                flag === 'price_includes_tax'
                  ? 'settings.tax.included'
                  : flag === 'applies_to_service_charge'
                    ? 'settings.tax.onService'
                    : 'settings.tax.active',
              )}
            </label>
          ))}
        </fieldset>
      ))}
      {invalid && <p className="text-sm text-danger">{t('settings.tax.invalidRate')}</p>}
      {canEdit && (
        <SaveBar
          mutation={save}
          disabled={invalid}
          onSave={() =>
            save.mutate({
              rules: rules.map(({ rateText, ...r }) => ({
                ...r,
                rate_bp: percentToBp(rateText) ?? 0,
              })),
            })
          }
        />
      )}
    </Card>
  )
}
