import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

const minutes = (v: string, max: number) => {
  const n = Number.parseInt(v, 10)
  return /^\d+$/.test(v) && n >= 1 && n <= max ? n : null
}

/** FR-KDS-004: when a ticket is late, and how long a bumped one can be called back. */
export function KitchenSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('kitchen')
  const [late, setLate] = useState(String(data.kitchen?.late_minutes ?? 15))
  const [recall, setRecall] = useState(String(data.kitchen?.recall_minutes ?? 30))
  const lateMin = minutes(late, 240)
  const recallMin = minutes(recall, 1440)
  return (
    <Card className="flex flex-col gap-4">
      <fieldset disabled={!canEdit} className="grid gap-3 sm:grid-cols-2">
        <TextInput
          label={t('settings.kitchen.late')}
          inputMode="numeric"
          value={late}
          invalid={lateMin === null}
          onChange={(e) => setLate(e.target.value)}
        />
        <TextInput
          label={t('settings.kitchen.recall')}
          inputMode="numeric"
          value={recall}
          invalid={recallMin === null}
          onChange={(e) => setRecall(e.target.value)}
        />
      </fieldset>
      {canEdit && (
        <SaveBar
          mutation={save}
          disabled={lateMin === null || recallMin === null}
          onSave={() =>
            lateMin &&
            recallMin &&
            save.mutate({ late_minutes: lateMin, recall_minutes: recallMin })
          }
        />
      )}
    </Card>
  )
}
