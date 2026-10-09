import { clsx } from 'clsx'
import { useDeferredValue, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert } from '../../components/ui'
import type { MenuItemOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { useCategories } from '../catalog/api'
import { useMenu } from './posApi'

/** FR-SAL-004: touch-first menu with category chips and search; sold-out items are greyed. */
export function MenuGrid({
  channelId,
  currency,
  onPick,
}: {
  channelId: string
  currency: string
  onPick: (item: MenuItemOut) => void
}) {
  const { t, i18n } = useTranslation()
  const menu = useMenu(channelId, i18n.language)
  const categories = useCategories().data ?? []
  const [q, setQ] = useState('')
  const [category, setCategory] = useState('')
  const search = useDeferredValue(q).trim().toLowerCase()
  const items = (menu.data ?? []).filter(
    (i) =>
      (!category || i.category_id === category) &&
      (!search || i.name.toLowerCase().includes(search) || i.sku.toLowerCase().includes(search)),
  )
  const used = new Set((menu.data ?? []).map((i) => i.category_id))
  const chips = categories.filter((c) => used.has(c.id))
  return (
    <section className="flex flex-col gap-3" aria-label={t('pos.menu')}>
      <TextInput
        label={t('pos.search')}
        type="search"
        maxLength={100}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className="flex gap-2 overflow-x-auto pb-1">
        <Chip active={!category} onClick={() => setCategory('')} label={t('pos.allCategories')} />
        {chips.map((c) => (
          <Chip
            key={c.id}
            active={category === c.id}
            onClick={() => setCategory(c.id)}
            label={c.name}
          />
        ))}
      </div>
      {menu.error && <Alert>{errorMessage(menu.error, t)}</Alert>}
      {menu.isSuccess && items.length === 0 && <p className="text-ink-soft">{t('pos.noItems')}</p>}
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
        {items.map((item) => (
          <li key={item.id}>
            <MenuButton
              item={item}
              price={formatMoney(item.price, currency, intlLocale(i18n.language))}
              onPick={onPick}
            />
          </li>
        ))}
      </ul>
    </section>
  )
}

function Chip({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={clsx(
        'min-h-11 shrink-0 rounded-full border px-4 text-sm font-bold',
        active ? 'border-accent bg-raised' : 'border-line-strong text-ink-soft',
      )}
    >
      {label}
    </button>
  )
}

function MenuButton({
  item,
  price,
  onPick,
}: {
  item: MenuItemOut
  price: string
  onPick: (item: MenuItemOut) => void
}) {
  const { t } = useTranslation()
  return (
    <button
      type="button"
      disabled={!item.is_available}
      onClick={() => onPick(item)}
      className="flex h-full min-h-24 w-full flex-col overflow-hidden rounded-xl border border-line bg-card text-left hover:bg-raised disabled:opacity-50"
    >
      {item.photo_upload_id && (
        <img
          src={`/api/v1/uploads/${item.photo_upload_id}`}
          alt=""
          loading="lazy"
          className="h-20 w-full object-cover"
        />
      )}
      <span className="flex flex-1 flex-col gap-1 p-2">
        <span className="font-bold leading-tight">{item.name}</span>
        <span className="text-sm text-ink-soft">
          {item.is_available ? price : t('pos.soldOut')}
        </span>
      </span>
    </button>
  )
}
