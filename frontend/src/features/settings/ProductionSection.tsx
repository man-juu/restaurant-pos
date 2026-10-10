import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

/** FR-PRD-008: whether open branch requests add to the sending kitchen's prep list. */
export function ProductionSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('production')
  const [on, setOn] = useState(data.production?.prep_includes_requests ?? true)
  return (
    <Card className="flex flex-col gap-4">
      <fieldset disabled={!canEdit}>
        <label className="flex min-h-11 items-center gap-2">
          <input
            type="checkbox"
            className="h-5 w-5 accent-[var(--accent)]"
            checked={on}
            onChange={(e) => setOn(e.target.checked)}
          />
          {t('settings.production.includeRequests')}
        </label>
        <p className="text-sm text-muted">{t('settings.production.help')}</p>
      </fieldset>
      {canEdit && (
        <SaveBar mutation={save} onSave={() => save.mutate({ prep_includes_requests: on })} />
      )}
    </Card>
  )
}
