import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { MenuItemOut, OfflinePackOut } from '../../../lib/api/types'
import { MenuGrid } from '../MenuGrid'
import { ModifierDialog } from '../ModifierDialog'
import { addToCart, type CartLine } from './cart'
import { OfflineCart } from './OfflineCart'
import type { OfflineState } from './useOffline'

/** FR-SAL-013: sell from the saved menu while there is no connection. Each finished order
 * waits in the queue on this device and uploads by itself when the connection returns. */
export function OfflineTill(props: {
  outletId: string
  channelId: string
  currency: string
  pack: OfflinePackOut
  offline: OfflineState
}) {
  const { t } = useTranslation()
  const [lines, setLines] = useState<CartLine[]>([])
  const [choosing, setChoosing] = useState<MenuItemOut>()
  const add = (item: MenuItemOut, optionIds: string[], note: string) => {
    setChoosing(undefined)
    setLines((ls) => addToCart(ls, { item, optionIds, note }))
  }
  const pick = (item: MenuItemOut) =>
    item.modifier_groups.length > 0 ? setChoosing(item) : add(item, [], '')
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
      <MenuGrid
        channelId={props.channelId}
        outletId={props.outletId}
        currency={props.currency}
        onPick={pick}
      />
      <div className="flex flex-col gap-3 lg:sticky lg:top-4 lg:self-start">
        <p className="text-sm text-ink-soft">{t('pos.offline.cartNote')}</p>
        <OfflineCart {...props} lines={lines} setLines={setLines} />
      </div>
      {choosing && (
        <ModifierDialog
          item={choosing}
          currency={props.currency}
          onAdd={(ids, note) => add(choosing, ids, note)}
          onClose={() => setChoosing(undefined)}
        />
      )}
    </div>
  )
}
