import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Button, StateBadge } from '../../components/ui'

/** One list row with an "Archived" badge and an Edit button for editors. */
export function EditableRow({
  children,
  archived,
  onEdit,
  indent = 0,
}: {
  children: ReactNode
  archived: boolean
  onEdit?: () => void
  indent?: number
}) {
  const { t } = useTranslation()
  return (
    <li
      style={{ marginInlineStart: `${Math.min(indent, 6) * 1.25}rem` }}
      className="flex min-h-12 items-center justify-between gap-2 rounded-xl border border-line bg-card px-3"
    >
      <span className="min-w-0">{children}</span>
      <span className="flex items-center gap-2">
        {archived && <StateBadge state="read_only" label={t('catalog.archived')} />}
        {onEdit && (
          <Button variant="ghost" onClick={onEdit}>
            {t('catalog.edit')}
          </Button>
        )}
      </span>
    </li>
  )
}
