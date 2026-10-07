import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Card } from '../../components/ui'
import type { ItemOut } from '../../lib/api/types'
import { SaveBar } from '../settings/shared'
import { useSaveItem, useUnits } from './api'
import { ConversionsEditor } from './ConversionsEditor'
import { IdentityFields, StockFields } from './ItemFields'
import { type ItemDraft, problems, toBody, toDraft } from './itemDraft'

export function ItemForm({
  item,
  canEdit,
  onSaved,
}: {
  item?: ItemOut
  canEdit: boolean
  onSaved: (id: string) => void
}) {
  const { t, i18n } = useTranslation()
  const units = useUnits()
  const save = useSaveItem(i18n.language)
  const [d, setD] = useState(() => toDraft(item))
  const set = (patch: Partial<ItemDraft>) => setD((old) => ({ ...old, ...patch }))
  const issues = problems(d)
  const fields = { d, set, issues, isNew: !item }
  const submit = () => {
    const body = toBody(d, item)
    const payload = item ? { ...body, version: item.version, is_active: d.is_active } : body
    save.mutate({ id: item?.id, body: payload }, { onSuccess: (saved) => onSaved(saved.id) })
  }

  return (
    <Card className="flex flex-col gap-4">
      <fieldset disabled={!canEdit} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <IdentityFields {...fields} />
        <StockFields {...fields} />
      </fieldset>
      <ConversionsEditor
        rows={d.conversions}
        units={(units.data ?? []).filter((u) => u.id !== d.base_unit_id)}
        disabled={!canEdit}
        invalid={issues.includes('conversion')}
        onChange={(conversions) => set({ conversions })}
      />
      {issues.length > 0 && (
        <p className="text-sm text-danger">
          {issues.map((p) => t(`catalog.item.problems.${p}`)).join(' ')}
        </p>
      )}
      {canEdit && <SaveBar mutation={save} disabled={issues.length > 0} onSave={submit} />}
    </Card>
  )
}
