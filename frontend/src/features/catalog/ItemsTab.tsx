import { useDeferredValue, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, StateBadge } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { type ItemFilter, useItems } from './api'
import { DataToolbar } from './DataToolbar'
import { ITEM_TYPES } from './labels'

export function ItemsTab({
  canCreate,
  onOpen,
  onCreate,
}: {
  canCreate: boolean
  onOpen: (id: string) => void
  onCreate: () => void
}) {
  const { t, i18n } = useTranslation()
  const [q, setQ] = useState('')
  const [type, setType] = useState<ItemFilter['type']>('')
  // Typing should not fire a request per key press; React defers the search value.
  const search = useDeferredValue(q)
  const items = useItems({ q: search, type, lang: i18n.language })
  const rows = items.data?.pages.flatMap((p) => p.items) ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_200px_auto] sm:items-end">
        <TextInput
          label={t('catalog.items.search')}
          type="search"
          maxLength={100}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <SelectInput
          label={t('catalog.items.type')}
          value={type}
          onChange={(e) => setType(e.target.value as ItemFilter['type'])}
        >
          <option value="">{t('catalog.items.allTypes')}</option>
          {ITEM_TYPES.map((k) => (
            <option key={k} value={k}>
              {t(`catalog.types.${k}`)}
            </option>
          ))}
        </SelectInput>
        {canCreate && <Button onClick={onCreate}>{t('catalog.items.new')}</Button>}
      </div>
      <DataToolbar canImport={canCreate} />
      {items.error && <Alert>{errorMessage(items.error, t)}</Alert>}
      {items.isSuccess && rows.length === 0 && (
        <p className="text-ink-soft">
          {t(q || type ? 'catalog.items.noMatch' : 'catalog.items.empty')}
        </p>
      )}
      <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {rows.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onOpen(item.id)}
              className="flex min-h-14 w-full items-center justify-between gap-3 rounded-xl border border-line bg-card px-4 py-2 text-left hover:bg-raised"
            >
              <Thumb uploadId={item.photo_upload_id ?? null} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-bold">{item.name}</span>
                <span className="block text-sm text-muted">
                  {item.sku} · {t(`catalog.types.${item.type}`)}
                </span>
              </span>
              {!item.is_active && <StateBadge state="read_only" label={t('catalog.archived')} />}
            </button>
          </li>
        ))}
      </ul>
      {items.hasNextPage && (
        <Button
          variant="ghost"
          onClick={() => items.fetchNextPage()}
          disabled={items.isFetchingNextPage}
          aria-busy={items.isFetchingNextPage}
        >
          {t('catalog.items.more')}
        </Button>
      )}
    </div>
  )
}

/** Optional photo (FR-CAT-001); a neutral tile when the item has none. */
function Thumb({ uploadId }: { uploadId: string | null }) {
  if (!uploadId) return <span aria-hidden className="size-10 shrink-0 rounded-lg bg-raised" />
  return (
    <img
      src={`/api/v1/uploads/${uploadId}`}
      alt=""
      loading="lazy"
      className="size-10 shrink-0 rounded-lg object-cover"
    />
  )
}
