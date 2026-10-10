import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, SelectInput, TextInput } from '../../components/form'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

const STEP = /^\d{1,6}$/
const DEFAULTS = {
  require_shift: true,
  tips_enabled: false,
  offline_enabled: true,
  cash_rounding_step: 0,
  void_stock_effect: 'waste' as 'waste' | 'none',
}

/** FR-SAL-006, 009: how the cashier screen works for this business. */
export function PosSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('pos')
  const pos = { ...DEFAULTS, ...data.pos }
  const [requireShift, setRequireShift] = useState(pos.require_shift)
  const [tips, setTips] = useState(pos.tips_enabled)
  const [offline, setOffline] = useState(pos.offline_enabled)
  const [step, setStep] = useState(String(pos.cash_rounding_step))
  const [voidEffect, setVoidEffect] = useState(pos.void_stock_effect)
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
        <CheckInput label={t('settings.pos.offline')} checked={offline} onChange={setOffline} />
        <TextInput
          label={t('settings.pos.roundingStep')}
          inputMode="numeric"
          value={step}
          invalid={!valid}
          onChange={(e) => setStep(e.target.value)}
        />
        <SelectInput
          label={t('settings.pos.voidEffect')}
          value={voidEffect}
          onChange={(e) => setVoidEffect(e.target.value as 'waste' | 'none')}
        >
          <option value="waste">{t('settings.pos.voidWaste')}</option>
          <option value="none">{t('settings.pos.voidNone')}</option>
        </SelectInput>
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
              offline_enabled: offline,
              cash_rounding_step: Number(step),
              void_stock_effect: voidEffect,
            })
          }
        />
      )}
    </Card>
  )
}
