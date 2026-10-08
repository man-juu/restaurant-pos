import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

/** FR-PUR-011: invoice photos are optional unless the owner requires them. */
export function PurchasingSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('purchasing')
  const [required, setRequired] = useState(data.purchasing?.require_invoice_attachment ?? false)
  return (
    <Card className="flex flex-col gap-4">
      <fieldset disabled={!canEdit}>
        <label className="flex min-h-11 items-center gap-2">
          <input
            type="checkbox"
            className="h-5 w-5 accent-[var(--accent)]"
            checked={required}
            onChange={(e) => setRequired(e.target.checked)}
          />
          {t('settings.purchasing.requireInvoice')}
        </label>
        <p className="text-sm text-muted">{t('settings.purchasing.help')}</p>
      </fieldset>
      {canEdit && (
        <SaveBar
          mutation={save}
          onSave={() => save.mutate({ require_invoice_attachment: required })}
        />
      )}
    </Card>
  )
}
