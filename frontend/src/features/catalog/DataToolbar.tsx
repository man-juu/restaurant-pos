import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ImportPanel } from '../../components/imports/ImportPanel'
import { Button } from '../../components/ui'
import { IMPORTS } from '../../lib/imports'
import { exportUrl } from './importApi'
import { ImportHistory } from './ImportHistory'

type Open = 'items' | 'recipes' | null

/** FR-IMP-003 export for everyone who can see items; imports for those who can create them. */
export function DataToolbar({ canImport }: { canImport: boolean }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState<Open>(null)
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3 text-sm font-semibold">
        <a className="text-accent underline" href={exportUrl('xlsx')}>
          {t('catalog.export.xlsx')}
        </a>
        <a className="text-accent underline" href={exportUrl('csv')}>
          {t('catalog.export.csv')}
        </a>
        {canImport && (
          <>
            <Button variant="ghost" onClick={() => setOpen('items')}>
              {t('catalog.import.open')}
            </Button>
            <Button variant="ghost" onClick={() => setOpen('recipes')}>
              {t('catalog.import.openRecipes')}
            </Button>
          </>
        )}
      </div>
      {open === 'items' && <ItemImport onClose={() => setOpen(null)} />}
      {open === 'recipes' && (
        <ImportPanel
          kind={IMPORTS.recipes}
          title={t('catalog.import.recipesTitle')}
          help={t('catalog.import.recipesHelp')}
          onClose={() => setOpen(null)}
        />
      )}
      {open && <ImportHistory />}
    </div>
  )
}

/** Items: owners choose whether unknown categories are created or reported as errors. */
function ItemImport({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation()
  const [create, setCreate] = useState(true)
  return (
    <ImportPanel
      key={String(create)} // a new choice re-checks from a fresh file pick
      kind={IMPORTS.items}
      title={t('catalog.import.title')}
      help={t('catalog.import.help')}
      options={{ create_categories: String(create) }}
      onClose={onClose}
    >
      <label className="flex min-h-11 items-center gap-3 text-sm">
        <input
          type="checkbox"
          className="h-5 w-5 accent-accent"
          checked={create}
          onChange={(e) => setCreate(e.target.checked)}
        />
        {t('catalog.import.createCategories')}
      </label>
    </ImportPanel>
  )
}
