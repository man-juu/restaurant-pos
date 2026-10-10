import { useState } from 'react'
import { useSearchParams } from 'react-router'
import { useTranslation } from 'react-i18next'

import { Alert } from '../../components/ui'
import type { MenuItemOut, PaymentMethod, PosSettings } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { MenuGrid } from './MenuGrid'
import { ModifierDialog } from './ModifierDialog'
import { OpenOrders } from './OpenOrders'
import { OrderView } from './OrderView'
import { useAddLine, useCreateOrder } from './posApi'

/** What this person may do at the till (the server checks every call again). */
export interface TillRights {
  pay: boolean
  discount: boolean
  void: boolean
  refund: boolean
  earn?: boolean // give loyalty points on the paid receipt
}

export interface TillProps {
  outletId: string
  channelId: string
  currency: string
  can: TillRights
  methods: PaymentMethod[]
  pos: PosSettings
}

/** Menu on the left, the order on the right (stacked on phones). Picking an item with no
 * order open starts one, so the cashier never has to press "new order" first. */
export function Till(props: TillProps) {
  const { t, i18n } = useTranslation()
  // A table's bill opens straight on the till (/pos?order=..., FR-TBL-002).
  const [params] = useSearchParams()
  const [orderId, setOrderId] = useState<string | undefined>(params.get('order') ?? undefined)
  const [choosing, setChoosing] = useState<MenuItemOut>()
  const create = useCreateOrder(i18n.language)
  const add = useAddLine(i18n.language)
  const start = async (label: string | null) => {
    const order = await create.mutateAsync({
      body: { outlet_id: props.outletId, channel_id: props.channelId, label: label || null },
      key: crypto.randomUUID(),
    })
    setOrderId(order.id)
    return order.id
  }
  const addItem = async (item: MenuItemOut, optionIds: string[], note: string) => {
    setChoosing(undefined)
    const id = orderId ?? (await start(null))
    const body = { item_id: item.id, qty: '1', option_ids: optionIds, note: note.trim() || null }
    add.mutate({ orderId: id, body, key: crypto.randomUUID() })
  }
  const pick = (item: MenuItemOut) =>
    item.modifier_groups.length > 0 ? setChoosing(item) : void addItem(item, [], '')
  const error = create.error ?? add.error
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_400px]">
      <MenuGrid
        channelId={props.channelId}
        outletId={props.outletId}
        currency={props.currency}
        onPick={pick}
      />
      <div className="flex flex-col gap-3 lg:sticky lg:top-4 lg:self-start">
        {error ? <Alert>{errorMessage(error, t)}</Alert> : null}
        {orderId ? (
          <OrderView {...props} orderId={orderId} onClose={() => setOrderId(undefined)} />
        ) : (
          <OpenOrders
            outletId={props.outletId}
            currency={props.currency}
            onOpen={setOrderId}
            onNew={(label) => void start(label)}
            creating={create.isPending}
          />
        )}
      </div>
      {choosing && (
        <ModifierDialog
          item={choosing}
          currency={props.currency}
          onAdd={(ids, note) => void addItem(choosing, ids, note)}
          onClose={() => setChoosing(undefined)}
        />
      )}
    </div>
  )
}
