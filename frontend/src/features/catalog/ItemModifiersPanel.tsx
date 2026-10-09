import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput } from '../../components/form'
import { Alert, Card } from '../../components/ui'
import type { ItemOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useCapabilities } from '../../lib/session'
import { SaveBar } from '../settings/shared'
import {
  useItemModifierGroups,
  useModifierGroups,
  useSetAvailability,
  useSetItemModifierGroups,
} from './modifierApi'

/** FR-CAT-003 on a menu item: sold-out switch and the modifier groups it offers. */
export function ItemModifiersPanel({ item, canEdit }: { item: ItemOut; canEdit: boolean }) {
  const { t } = useTranslation()
  const caps = useCapabilities(true)
  const canToggle = Boolean(caps.data?.permissions.includes('catalog.item.availability'))
  const availability = useSetAvailability(item.id)
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-xl font-bold">{t('catalog.modifiers.title')}</h2>
      <CheckInput
        label={t('catalog.modifiers.available')}
        checked={item.is_available ?? true}
        disabled={!canToggle || availability.isPending}
        onChange={(v) => availability.mutate(v)}
      />
      {availability.error ? <Alert>{errorMessage(availability.error, t)}</Alert> : null}
      <GroupPicker itemId={item.id} canEdit={canEdit} />
    </Card>
  )
}

function GroupPicker({ itemId, canEdit }: { itemId: string; canEdit: boolean }) {
  const { t } = useTranslation()
  const all = useModifierGroups()
  const linked = useItemModifierGroups(itemId)
  if (!all.data || !linked.data) return null
  return (
    <GroupChoices
      key={linked.data.map((g) => g.id).join()}
      itemId={itemId}
      canEdit={canEdit}
      groups={all.data.filter((g) => g.is_active)}
      initial={linked.data.map((g) => g.id)}
      empty={t('catalog.modifiers.empty')}
    />
  )
}

function GroupChoices({
  itemId,
  canEdit,
  groups,
  initial,
  empty,
}: {
  itemId: string
  canEdit: boolean
  groups: { id: string; name: string }[]
  initial: string[]
  empty: string
}) {
  const save = useSetItemModifierGroups(itemId)
  const [picked, setPicked] = useState(initial)
  const toggle = (id: string, on: boolean) =>
    setPicked((old) => (on ? [...old, id] : old.filter((g) => g !== id)))
  if (groups.length === 0) return <p className="text-sm text-ink-soft">{empty}</p>
  return (
    <>
      <ul className="grid gap-1 sm:grid-cols-2">
        {groups.map((g) => (
          <li key={g.id}>
            <CheckInput
              label={g.name}
              checked={picked.includes(g.id)}
              disabled={!canEdit}
              onChange={(on) => toggle(g.id, on)}
            />
          </li>
        ))}
      </ul>
      {canEdit && <SaveBar mutation={save} onSave={() => save.mutate(picked)} />}
    </>
  )
}
