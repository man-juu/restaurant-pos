import { useState } from 'react'

import type { Capabilities, PosSettings } from '../../lib/api/types'
import { useOutlets } from '../../lib/session'
import { useChannels } from '../catalog/api'
import { useSettings } from '../settings/api'
import { useCurrentShift } from './posApi'

const DEFAULT_POS: PosSettings = {
  require_shift: true,
  cash_rounding_step: 0,
  tips_enabled: false,
  offline_enabled: true,
  void_stock_effect: 'waste',
}

/** A pick that falls back to the first option until the user chooses. */
function usePick(first: string | undefined) {
  const [picked, setPicked] = useState('')
  return [picked || first || '', setPicked] as const
}

function usePlace() {
  const outlets = (useOutlets().data ?? []).filter((o) => o.is_active)
  const channels = useChannels().data ?? []
  const [outletId, setOutlet] = usePick(outlets[0]?.id)
  const [channelId, setChannel] = usePick(channels[0]?.id)
  return { outlets, channels, outletId, setOutlet, channelId, setChannel }
}

function useTillSettings() {
  const data = useSettings().data
  const methods = data?.payment_methods.methods ?? []
  return { pos: data?.pos ?? DEFAULT_POS, methods: methods.filter((m) => m.active !== false) }
}

/** Everything the till screen needs before it can take an order. UI only: the server
 * checks permissions, outlet scope and the shift rule again on every call. */
export function useTillContext(caps?: Capabilities) {
  const permissions = caps?.permissions ?? []
  const has = (code: string) => permissions.includes(code)
  const can = {
    pay: has('sales.order.pay'),
    discount: has('sales.discount.apply'),
    void: has('sales.order.void'),
    refund: has('sales.order.refund'),
  }
  const place = usePlace()
  const { pos, methods } = useTillSettings()
  const shift = useCurrentShift(place.outletId, has('sales.shift.open'))
  // Payments need an open shift unless the business switched that off (FR-SAL-009).
  const needsShift = can.pay && pos.require_shift !== false && shift.isSuccess && !shift.data
  return {
    ...place,
    can,
    currency: caps?.currency ?? 'IDR',
    pos,
    methods,
    shift: shift.data ?? null,
    needsShift,
  }
}

export type TillContext = ReturnType<typeof useTillContext>
