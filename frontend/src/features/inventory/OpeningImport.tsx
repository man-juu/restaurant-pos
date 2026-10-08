import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ImportPanel } from '../../components/imports/ImportPanel'
import { Button } from '../../components/ui'
import { IMPORTS } from '../../lib/imports'

/** FR-IMP-001: opening stock for many items and outlets from one file, on the chosen date. */
export function OpeningImport({ businessDate }: { businessDate: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  if (!open)
    return (
      <Button variant="ghost" onClick={() => setOpen(true)}>
        {t('inventory.opening.importOpen')}
      </Button>
    )
  return (
    <ImportPanel
      key={businessDate}
      kind={IMPORTS.opening}
      title={t('inventory.opening.importTitle')}
      help={t('inventory.opening.importHelp')}
      options={{ business_date: businessDate }}
      onClose={() => setOpen(false)}
    />
  )
}
