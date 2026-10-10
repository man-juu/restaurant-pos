import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Card, Field } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

function Check({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="flex min-h-11 items-center gap-2">
      <input
        type="checkbox"
        className="h-5 w-5 accent-[var(--accent)]"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  )
}

/** FR-PUR-011 invoice photos; FR-PUR-009 how strict the bill check is. */
export function PurchasingSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('purchasing')
  const p = data.purchasing
  const [required, setRequired] = useState(p?.require_invoice_attachment ?? false)
  const [block, setBlock] = useState(p?.block_mismatched_payment ?? false)
  const [tolerance, setTolerance] = useState(String((p?.bill_price_tolerance_bp ?? 0) / 100))
  const bp = Math.round(Number(tolerance.replace(',', '.')) * 100)
  return (
    <Card className="flex flex-col gap-4">
      <fieldset disabled={!canEdit} className="flex flex-col gap-3">
        <Check
          label={t('settings.purchasing.requireInvoice')}
          checked={required}
          onChange={setRequired}
        />
        <p className="text-sm text-muted">{t('settings.purchasing.help')}</p>
        <Field
          label={t('settings.purchasing.tolerance')}
          inputMode="decimal"
          value={tolerance}
          onChange={(e) => setTolerance(e.target.value)}
        />
        <Check label={t('settings.purchasing.blockMismatch')} checked={block} onChange={setBlock} />
        <p className="text-sm text-muted">{t('settings.purchasing.matchHelp')}</p>
      </fieldset>
      {canEdit && (
        <SaveBar
          mutation={save}
          onSave={() =>
            save.mutate({
              require_invoice_attachment: required,
              block_mismatched_payment: block,
              bill_price_tolerance_bp: Number.isFinite(bp) ? Math.min(Math.max(bp, 0), 10000) : 0,
            })
          }
        />
      )}
    </Card>
  )
}
