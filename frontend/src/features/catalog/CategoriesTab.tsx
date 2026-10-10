import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { CategoryOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { SaveBar } from '../settings/shared'
import { useCategories, useSaveCategory } from './api'
import { EditableRow } from './EditableRow'
import { treeOrder } from './tree'

export function CategoriesTab({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const categories = useCategories()
  const [editing, setEditing] = useState<CategoryOut | 'new'>()
  const all = categories.data ?? []

  return (
    <div className="flex flex-col gap-4">
      {categories.error && <Alert>{errorMessage(categories.error, t)}</Alert>}
      <CategoryList all={all} onEdit={canEdit ? setEditing : undefined} />
      {canEdit && !editing && (
        <div>
          <Button onClick={() => setEditing('new')}>{t('catalog.categories.new')}</Button>
        </div>
      )}
      {editing === 'new' && <CategoryForm all={all} onDone={() => setEditing(undefined)} />}
      {editing && editing !== 'new' && (
        <CategoryForm
          key={editing.id}
          category={editing}
          all={all}
          onDone={() => setEditing(undefined)}
        />
      )}
    </div>
  )
}

function CategoryList({
  all,
  onEdit,
}: {
  all: CategoryOut[]
  onEdit?: (row: CategoryOut) => void
}) {
  const { t } = useTranslation()
  if (all.length === 0) return <p className="text-ink-soft">{t('catalog.categories.empty')}</p>
  return (
    <ul className="flex flex-col gap-2">
      {treeOrder(all).map(({ row, depth }) => (
        <EditableRow
          key={row.id}
          indent={depth}
          archived={!row.is_active}
          onEdit={onEdit && (() => onEdit(row))}
        >
          <span className="font-semibold">{row.name}</span>
        </EditableRow>
      ))}
    </ul>
  )
}

function CategoryForm({
  category,
  all,
  onDone,
}: {
  category?: CategoryOut
  all: CategoryOut[]
  onDone: () => void
}) {
  const { t } = useTranslation()
  const save = useSaveCategory()
  const [name, setName] = useState(category?.name ?? '')
  const [parent, setParent] = useState(category?.parent_id ?? '')
  const [active, setActive] = useState(category?.is_active ?? true)
  const body = {
    name: name.trim(),
    parent_id: parent || null,
    sort_order: category?.sort_order ?? 0,
    is_active: active,
  }

  return (
    <Card className="grid gap-3 sm:grid-cols-3 sm:items-end">
      <TextInput
        label={t('catalog.categories.name')}
        value={name}
        maxLength={120}
        onChange={(e) => setName(e.target.value)}
      />
      <SelectInput
        label={t('catalog.categories.parent')}
        value={parent}
        onChange={(e) => setParent(e.target.value)}
      >
        <option value="">{t('catalog.categories.top')}</option>
        {all
          .filter((c) => c.id !== category?.id)
          .map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
      </SelectInput>
      <CheckInput label={t('catalog.item.active')} checked={active} onChange={setActive} />
      <div className="flex flex-wrap gap-3 sm:col-span-3">
        <SaveBar
          mutation={save}
          disabled={!body.name}
          onSave={() => save.mutate({ id: category?.id, body }, { onSuccess: onDone })}
        />
        <Button variant="ghost" onClick={onDone}>
          {t('catalog.cancel')}
        </Button>
      </div>
    </Card>
  )
}
