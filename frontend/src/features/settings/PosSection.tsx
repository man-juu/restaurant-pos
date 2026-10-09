import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, TextInput } from '../../components/form'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

const STEP = /^\d{1,6}$/

/** FR-SAL-006, 009: how the cashier screen works for this business. */
export function PosSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('pos')
  const [requireShift, setRequireShift] = useState(data.pos?.require_shift ?? true)
  const [tips, setTips] = useState(data.pos?.tips_enabled ?? false)
  const [step, setStep] = useState(String(data.pos?.cash_rounding_step ?? 0))
  const valid = STEP.test(step) && Number(step) <= 100_000
  return (
    <Card className="flex flex-col gap-4">
      <fieldset disabled={!canEdit} className="flex flex-col gap-3">
        <CheckInput
          label={t('settings.pos.requireShift')}
          checked={requireShift}
          onChange={setRequireShift}
        />
        <CheckInput label={t('settings.pos.tips')} checked={tips} onChange={setTips} />
        <TextInput
          label={t('settings.pos.roundingStep')}
          inputMode="numeric"
          value={step}
          invalid={!valid}
          onChange={(e) => setStep(e.target.value)}
        />
        <p className="text-sm text-muted">{t('settings.pos.help')}</p>
      </fieldset>
      {canEdit && (
        <SaveBar
          mutation={save}
          disabled={!valid}
          onSave={() =>
            save.mutate({
              require_shift: requireShift,
              tips_enabled: tips,
              cash_rounding_step: Number(step),
            })
          }
        />
      )}
    </Card>
  )
}
