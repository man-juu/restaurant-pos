import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { Tabs } from '../../components/form'
import type { Capabilities } from '../../lib/api/types'
import { CategoriesTab } from './CategoriesTab'
import { ChannelsTab } from './ChannelsTab'
import { ItemEditor } from './ItemEditor'
import { ItemsTab } from './ItemsTab'
import { UnitsTab } from './UnitsTab'

const TABS = ['items', 'categories', 'units', 'channels'] as const
type Tab = (typeof TABS)[number]

/** What the UI offers; the server checks every call again (CLAUDE.md rule 2). */
function access(caps?: Capabilities) {
  const has = (code: string) => Boolean(caps?.permissions.includes(code))
  return {
    canEdit: has('catalog.item.update'),
    canCreate: has('catalog.item.create'),
    currency: caps?.currency ?? 'IDR',
  }
}

/** FR-CAT-001 to 004: items, categories, units, channels and prices. */
export function CatalogPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const { canEdit, canCreate, currency } = access(caps)
  const [tab, setTab] = useState<Tab>('items')
  // undefined: list; 'new': empty form; otherwise the id of the item being edited.
  const [editing, setEditing] = useState<string>()

  if (editing)
    return (
      <ItemEditor
        itemId={editing === 'new' ? undefined : editing}
        canEdit={editing === 'new' ? canCreate : canEdit}
        currency={currency}
        onSaved={setEditing}
        onClose={() => setEditing(undefined)}
      />
    )

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('catalog.title')}</h1>
      {!canEdit && <p className="text-sm text-ink-soft">{t('catalog.readOnly')}</p>}
      <Tabs tabs={TABS} value={tab} onChange={setTab} label={(k) => t(`catalog.tabs.${k}`)} />
      <div role="tabpanel">
        {tab === 'items' && (
          <ItemsTab canCreate={canCreate} onOpen={setEditing} onCreate={() => setEditing('new')} />
        )}
        {tab === 'categories' && <CategoriesTab canEdit={canEdit} />}
        {tab === 'units' && <UnitsTab canEdit={canEdit} />}
        {tab === 'channels' && <ChannelsTab canEdit={canEdit} />}
      </div>
    </div>
  )
}
