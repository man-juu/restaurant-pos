import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { labelsUrl } from './api'

const MAX = 50

/** FR-PRD-007: print shelf-life labels for what was made. */
export function LabelLink({ orderId }: { orderId: string }) {
  const { t, i18n } = useTranslation()
  const [copies, setCopies] = useState('1')
  const count = Math.min(Math.max(Number.parseInt(copies, 10) || 1, 1), MAX)
  return (
    <div className="flex flex-wrap items-end gap-3">
      <TextInput
        label={t('production.labels.copies')}
        inputMode="numeric"
        className="w-28"
        value={copies}
        onChange={(e) => setCopies(e.target.value)}
      />
      <a
        className="pb-2 text-sm font-semibold text-accent underline"
        href={labelsUrl(orderId, count, i18n.language)}
        target="_blank"
        rel="noreferrer"
      >
        {t('production.labels.print', { count })}
      </a>
    </div>
  )
}
