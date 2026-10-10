import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { bpToPercent, percentToBp } from '../../lib/percent'
import { useSaveSetting } from './api'
import { SaveBar, inputClass } from './shared'

export function ServiceSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t, i18n } = useTranslation()
  const save = useSaveSetting('service_charge')
  const [enabled, setEnabled] = useState(data.service_charge.enabled ?? false)
  const [rate, setRate] = useState(bpToPercent(data.service_charge.rate_bp ?? 0, i18n.language))
  const bp = percentToBp(rate)
  return (
    <Card className="flex flex-col gap-4">
      <fieldset disabled={!canEdit} className="flex flex-wrap items-end gap-4">
        <label className="flex min-h-11 items-center gap-2">
          <input
            type="checkbox"
            className="h-5 w-5 accent-[var(--accent)]"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          {t('settings.service.enabled')}
        </label>
        <label className="flex flex-col gap-1 text-sm font-semibold text-ink-soft">
          {t('settings.service.rate')}
          <input
            className={inputClass}
            inputMode="decimal"
            value={rate}
            aria-invalid={bp === null}
            onChange={(e) => setRate(e.target.value)}
          />
        </label>
      </fieldset>
      {canEdit && (
        <SaveBar
          mutation={save}
          disabled={bp === null}
          onSave={() => save.mutate({ ...data.service_charge, enabled, rate_bp: bp ?? 0 })}
        />
      )}
    </Card>
  )
}

export function PaymentsSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('payment_methods')
  const [methods, setMethods] = useState(data.payment_methods.methods ?? [])
  return (
    <Card className="flex flex-col gap-3">
      {methods.map((m, i) => (
        <label
          key={m.code}
          className="flex min-h-11 items-center justify-between gap-3 rounded-xl border border-line px-3"
        >
          <span>
            <span className="font-bold">{m.name}</span>{' '}
            <span className="text-sm text-muted">{t(`settings.payments.kinds.${m.kind}`)}</span>
          </span>
          <input
            type="checkbox"
            className="h-5 w-5 accent-[var(--accent)]"
            disabled={!canEdit}
            checked={m.active ?? true}
            aria-label={t('settings.payments.active')}
            onChange={(e) =>
              setMethods((all) =>
                all.map((x, j) => (j === i ? { ...x, active: e.target.checked } : x)),
              )
            }
          />
        </label>
      ))}
      {canEdit && <SaveBar mutation={save} onSave={() => save.mutate({ methods })} />}
    </Card>
  )
}

export function NumberingSection({ data }: { data: AllSettings }) {
  const { t } = useTranslation()
  const year = new Date().getFullYear()
  return (
    <Card className="overflow-x-auto p-0">
      <table className="w-full min-w-[480px] text-sm">
        <thead>
          <tr className="text-left text-xs tracking-wider text-muted uppercase">
            <th className="px-4 py-3">{t('settings.numbering.document')}</th>
            <th className="px-4 py-3">{t('settings.numbering.prefix')}</th>
            <th className="px-4 py-3">{t('settings.numbering.example')}</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(data.numbering.formats ?? {}).map(([doc, f]) => (
            <tr key={doc} className="border-t border-line">
              <td className="px-4 py-3">
                {t(`settings.numbering.docs.${doc}`, { defaultValue: doc })}
              </td>
              <td className="px-4 py-3 font-mono">{f.prefix}</td>
              <td className="px-4 py-3 font-mono text-ink-soft">
                {`${f.prefix}${f.reset === 'never' ? '' : `-${year}`}-${'1'.padStart(f.padding ?? 5, '0')}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  )
}
