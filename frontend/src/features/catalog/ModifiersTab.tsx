import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import type { ModifierGroupOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { EditableRow } from './EditableRow'
import { ModifierGroupForm } from './ModifierGroupForm'
import { useModifierGroups } from './modifierApi'

/** FR-CAT-003: choices offered on menu items (size, add-ons, spice level). */
export function ModifiersTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const groups = useModifierGroups()
  const [editing, setEditing] = useState<ModifierGroupOut | 'new'>()

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('catalog.modifiers.help')}</p>
      {groups.error && <Alert>{errorMessage(groups.error, t)}</Alert>}
      {groups.isSuccess && groups.data.length === 0 && (
        <p className="text-ink-soft">{t('catalog.modifiers.empty')}</p>
      )}
      <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {groups.data?.map((g) => (
          <EditableRow
            key={g.id}
            archived={!g.is_active}
            onEdit={canEdit ? () => setEditing(g) : undefined}
          >
            <b>{g.name}</b>{' '}
            <span className="text-sm text-muted">
              {g.options
                .filter((o) => o.is_active)
                .map((o) => o.name)
                .join(', ')}
            </span>
          </EditableRow>
        ))}
      </ul>
      {canEdit && !editing && (
        <div>
          <Button onClick={() => setEditing('new')}>{t('catalog.modifiers.new')}</Button>
        </div>
      )}
      {editing && (
        <ModifierGroupForm
          key={editing === 'new' ? 'new' : editing.id}
          group={editing === 'new' ? undefined : editing}
          onDone={() => setEditing(undefined)}
        />
      )}
    </div>
  )
}
