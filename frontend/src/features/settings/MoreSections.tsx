import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, TextInput } from '../../components/form'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

type Props = { data: AllSettings; canEdit: boolean }
const minutes = (v: string, fallback: number) => Number.parseInt(v, 10) || fallback

/** FR-TBL-006 to 008: how long a party usually stays, when a booking counts as late, and
 *  whether a table may be booked twice for the same time. */
export function TablesSection({ data, canEdit }: Props) {
  const { t } = useTranslation()
  const save = useSaveSetting('tables')
  const cur = data.tables
  const [dwell, setDwell] = useState(String(cur?.default_dwell_minutes ?? 90))
  const [late, setLate] = useState(String(cur?.no_show_after_minutes ?? 15))
  const [over, setOver] = useState(cur?.allow_overbooking ?? false)
  return (
    <Card className="flex flex-col gap-3">
      <fieldset disabled={!canEdit} className="flex flex-col gap-3">
        <TextInput
          label={t('settings.tables.dwell')}
          inputMode="numeric"
          value={dwell}
          onChange={(e) => setDwell(e.target.value)}
        />
        <TextInput
          label={t('settings.tables.late')}
          inputMode="numeric"
          value={late}
          onChange={(e) => setLate(e.target.value)}
        />
        <CheckInput label={t('settings.tables.overbooking')} checked={over} onChange={setOver} />
      </fieldset>
      {canEdit && (
        <SaveBar
          mutation={save}
          onSave={() =>
            save.mutate({
              default_dwell_minutes: minutes(dwell, 90),
              no_show_after_minutes: minutes(late, 15),
              allow_overbooking: over,
            })
          }
        />
      )}
    </Card>
  )
}

/** FR-FIN-003: journal operations automatically once the books are set up. */
export function FinanceSection({ data, canEdit }: Props) {
  const { t } = useTranslation()
  const save = useSaveSetting('finance')
  const [auto, setAuto] = useState(data.finance?.auto_journals ?? true)
  return (
    <Card className="flex flex-col gap-3">
      <fieldset disabled={!canEdit}>
        <CheckInput label={t('settings.finance.auto')} checked={auto} onChange={setAuto} />
        <p className="text-sm text-muted">{t('settings.finance.help')}</p>
      </fieldset>
      {canEdit && <SaveBar mutation={save} onSave={() => save.mutate({ auto_journals: auto })} />}
    </Card>
  )
}
