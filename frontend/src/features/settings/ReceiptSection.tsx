import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput } from '../../components/form'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

/** FR-SAL-010: lines above and below the sale, and the printer paper width. */
export function ReceiptSection({ data, canEdit }: { data: AllSettings; canEdit: boolean }) {
  const { t } = useTranslation()
  const save = useSaveSetting('receipt')
  const [header, setHeader] = useState(data.receipt?.header ?? '')
  const [footer, setFooter] = useState(data.receipt?.footer ?? '')
  const [paper, setPaper] = useState<58 | 80>(data.receipt?.paper_mm === 80 ? 80 : 58)
  return (
    <Card className="flex flex-col gap-4">
      <fieldset disabled={!canEdit} className="flex flex-col gap-3">
        <TextArea label={t('settings.receipt.header')} value={header} onChange={setHeader} />
        <TextArea label={t('settings.receipt.footer')} value={footer} onChange={setFooter} />
        <SelectInput
          label={t('settings.receipt.paper')}
          value={String(paper)}
          onChange={(e) => setPaper(e.target.value === '80' ? 80 : 58)}
        >
          <option value="58">{t('settings.receipt.mm', { mm: 58 })}</option>
          <option value="80">{t('settings.receipt.mm', { mm: 80 })}</option>
        </SelectInput>
        <p className="text-sm text-muted">{t('settings.receipt.help')}</p>
      </fieldset>
      {canEdit && (
        <SaveBar mutation={save} onSave={() => save.mutate({ header, footer, paper_mm: paper })} />
      )}
    </Card>
  )
}

function TextArea({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (v: string) => void
}) {
  return (
    <label className="flex flex-col gap-1 text-sm font-semibold">
      {label}
      <textarea
        className="min-h-20 rounded-xl border border-line-strong bg-card p-3 font-normal"
        maxLength={300}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  )
}
