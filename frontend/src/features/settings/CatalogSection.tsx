import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { bpToPercent, optionalPercentOk, percentToBp } from '../../lib/percent'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

/** FR-CAT-012: default food cost target; items may set their own. Empty turns the alert off. */
export function CatalogSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t, i18n } = useTranslation()
  const save = useSaveSetting('catalog')
  const [pct, setPct] = useState(() => {
    const bp = data.catalog?.target_food_cost_bp
    return bp == null ? '' : bpToPercent(bp, i18n.language)
  })
  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('settings.catalog.help')}</p>
      <fieldset disabled={!canEdit} className="max-w-xs">
        <TextInput
          label={t('settings.catalog.target')}
          inputMode="decimal"
          value={pct}
          invalid={!optionalPercentOk(pct)}
          onChange={(e) => setPct(e.target.value)}
        />
      </fieldset>
      {canEdit && (
        <SaveBar
          mutation={save}
          onSave={() =>
            optionalPercentOk(pct) &&
            save.mutate({ target_food_cost_bp: pct.trim() ? percentToBp(pct) : null })
          }
        />
      )}
    </Card>
  )
}
