import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '../../components/ui'
import { exportUrl } from './importApi'
import { ImportPanel } from './ImportPanel'

/** FR-IMP-003 export for everyone who can see items; import for those who can create them. */
export function DataToolbar({ canImport }: { canImport: boolean }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 text-sm font-semibold">
        <a className="text-accent underline" href={exportUrl('xlsx')}>
          {t('catalog.export.xlsx')}
        </a>
        <a className="text-accent underline" href={exportUrl('csv')}>
          {t('catalog.export.csv')}
        </a>
        {canImport && !open && (
          <Button variant="ghost" onClick={() => setOpen(true)}>
            {t('catalog.import.open')}
          </Button>
        )}
      </div>
      {open && <ImportPanel onClose={() => setOpen(false)} />}
    </div>
  )
}
