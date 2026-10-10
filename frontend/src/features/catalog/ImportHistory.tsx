import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useImports, useRevertImport } from './importApi'

/** FR-IMP-002: past imports; undo archives the items an import created. */
export function ImportHistory() {
  const { t, i18n } = useTranslation()
  const imports = useImports()
  const revert = useRevertImport()
  if (!imports.data?.length) return null
  return (
    <div className="flex flex-col gap-2 border-t border-line pt-3">
      <h3 className="font-bold">{t('catalog.import.history')}</h3>
      {revert.error ? <Alert>{errorMessage(revert.error, t)}</Alert> : null}
      <ul className="flex flex-col gap-2 text-sm">
        {imports.data.map((b) => (
          <li key={b.id} className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {b.file_name} · {t('catalog.import.rows', { count: b.row_count })} ·{' '}
              {new Date(b.created_at).toLocaleString(i18n.language)}
            </span>
            {b.status === 'committed' ? (
              <Button
                variant="ghost"
                onClick={() => revert.mutate(b.id)}
                disabled={revert.isPending}
              >
                {t('catalog.import.undo')}
              </Button>
            ) : (
              <span className="text-muted">{t('catalog.import.undone')}</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
