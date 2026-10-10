import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

type Mode = 'cost' | 'cost_plus'

/** FR-TRF-006: whether outlets charge each other for goods they send, and the markup. */
export function TransfersSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('transfers')
  const [mode, setMode] = useState<Mode>(data.transfers?.price_mode ?? 'cost')
  const [pct, setPct] = useState(String((data.transfers?.markup_bp ?? 0) / 100))
  const bp = Math.max(0, Math.round(Number(pct.replace(',', '.')) * 100) || 0)
  return (
    <Card className="flex flex-col gap-3">
      <fieldset disabled={!canEdit} className="flex flex-col gap-3">
        <SelectInput
          label={t('settings.transfers.mode')}
          value={mode}
          onChange={(e) => setMode(e.target.value as Mode)}
        >
          <option value="cost">{t('settings.transfers.cost')}</option>
          <option value="cost_plus">{t('settings.transfers.costPlus')}</option>
        </SelectInput>
        {mode === 'cost_plus' && (
          <TextInput
            label={t('settings.transfers.markup')}
            inputMode="decimal"
            value={pct}
            onChange={(e) => setPct(e.target.value)}
          />
        )}
        <p className="text-sm text-muted">{t('settings.transfers.help')}</p>
      </fieldset>
      {canEdit && (
        <SaveBar mutation={save} onSave={() => save.mutate({ price_mode: mode, markup_bp: bp })} />
      )}
    </Card>
  )
}
