import { useDeferredValue, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { ItemSummary } from '../../lib/api/types'
import { useItems } from './api'

const MAX_RESULTS = 8

/** Search ingredients and semi-finished items to add to a recipe. */
export function ComponentPicker({
  exclude,
  onPick,
}: {
  exclude: Set<string>
  onPick: (item: ItemSummary) => void
}) {
  const { t, i18n } = useTranslation()
  const [q, setQ] = useState('')
  const search = useDeferredValue(q)
  const items = useItems({ q: search, type: '', lang: i18n.language })
  const results = (items.data?.pages[0]?.items ?? [])
    .filter((i) => i.is_active && i.type !== 'menu' && !exclude.has(i.id))
    .slice(0, MAX_RESULTS)

  return (
    <div className="flex flex-col gap-2">
      <TextInput
        label={t('catalog.recipe.addComponent')}
        type="search"
        maxLength={100}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {search.trim() !== '' && (
        <ul className="flex flex-col gap-1">
          {results.length === 0 && (
            <li className="text-sm text-ink-soft">{t('catalog.items.noMatch')}</li>
          )}
          {results.map((item) => (
            <li key={item.id}>
              <Button
                variant="ghost"
                className="w-full justify-between"
                onClick={() => {
                  onPick(item)
                  setQ('')
                }}
              >
                <span className="truncate">{`${item.name} (${item.sku})`}</span>
                <span className="text-xs text-muted">{t(`catalog.types.${item.type}`)}</span>
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
