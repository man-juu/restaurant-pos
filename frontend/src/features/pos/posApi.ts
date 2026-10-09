import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type {
  MenuItemOut,
  PosOrderOut,
  PosOrderSummary,
  PosPayIn,
  ShiftOut,
} from '../../lib/api/types'

const POS = '/api/v1/pos'
const lang2 = (lang: string) => lang.slice(0, 2)
const keyed = (key: string) => ({ 'Idempotency-Key': key })

export const useMenu = (channelId: string, lang: string) =>
  useQuery({
    queryKey: ['pos-menu', channelId, lang2(lang)],
    queryFn: () =>
      request<MenuItemOut[]>(
        'GET',
        `/api/v1/catalog/menu?channel_id=${channelId}&lang=${lang2(lang)}`,
      ),
    enabled: Boolean(channelId),
    staleTime: 60_000, // docs/04: the till keeps the menu cached and refreshes it
  })

export const useOpenOrders = (outletId: string) =>
  useQuery({
    queryKey: ['pos-orders', outletId],
    queryFn: () => request<PosOrderSummary[]>('GET', `${POS}/orders?outlet_id=${outletId}`),
    enabled: Boolean(outletId),
    refetchInterval: 15_000, // other tills and waiters add orders
  })

export const useOrder = (id: string | undefined, lang: string) =>
  useQuery({
    queryKey: ['pos-order', id, lang2(lang)],
    queryFn: () => request<PosOrderOut>('GET', `${POS}/orders/${id}?lang=${lang2(lang)}`),
    enabled: Boolean(id),
  })

/** Every order change returns the whole order: put it in the cache, refresh the list. */
function useOrderChange<V>(lang: string, fn: (vars: V) => Promise<PosOrderOut>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (order) => {
      client.setQueryData(['pos-order', order.id, lang2(lang)], order)
      return client.invalidateQueries({ queryKey: ['pos-orders'] })
    },
  })
}

export const useCreateOrder = (lang: string) =>
  useOrderChange(
    lang,
    ({
      body,
      key,
    }: {
      body: { outlet_id: string; channel_id: string; label?: string | null }
      key: string
    }) => request<PosOrderOut>('POST', `${POS}/orders?lang=${lang2(lang)}`, body, keyed(key)),
  )

export interface LineBody {
  item_id: string
  qty: string
  option_ids: string[]
  note?: string | null
}

export const useAddLine = (lang: string) =>
  useOrderChange(lang, ({ orderId, body, key }: { orderId: string; body: LineBody; key: string }) =>
    request<PosOrderOut>(
      'POST',
      `${POS}/orders/${orderId}/lines?lang=${lang2(lang)}`,
      body,
      keyed(key),
    ),
  )

export const useChangeLine = (orderId: string, lang: string) =>
  useOrderChange(lang, ({ lineId, qty }: { lineId: string; qty: string | null }) =>
    qty === null
      ? request<PosOrderOut>(
          'DELETE',
          `${POS}/orders/${orderId}/lines/${lineId}?lang=${lang2(lang)}`,
        )
      : request<PosOrderOut>(
          'PUT',
          `${POS}/orders/${orderId}/lines/${lineId}?lang=${lang2(lang)}`,
          {
            qty,
          },
        ),
  )

export const useOrderStep = (orderId: string, lang: string) =>
  useOrderChange(lang, (step: 'send' | 'cancel') =>
    request<PosOrderOut>('POST', `${POS}/orders/${orderId}/${step}?lang=${lang2(lang)}`),
  )

export function usePay(orderId: string, lang: string) {
  const client = useQueryClient()
  const change = useOrderChange(lang, ({ body, key }: { body: PosPayIn; key: string }) =>
    request<PosOrderOut>(
      'POST',
      `${POS}/orders/${orderId}/pay?lang=${lang2(lang)}`,
      body,
      keyed(key),
    ),
  )
  return {
    ...change,
    mutate: (vars: { body: PosPayIn; key: string }, opts?: { onSuccess?: () => void }) =>
      change.mutate(vars, {
        onSuccess: () => {
          void client.invalidateQueries({ queryKey: ['pos-shift'] })
          opts?.onSuccess?.()
        },
      }),
  }
}

export const useCurrentShift = (outletId: string, enabled: boolean) =>
  useQuery({
    queryKey: ['pos-shift', outletId],
    queryFn: () => request<ShiftOut | null>('GET', `${POS}/shifts/current?outlet_id=${outletId}`),
    enabled: enabled && Boolean(outletId),
  })

function useShiftChange<V>(fn: (vars: V) => Promise<ShiftOut>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (shift) =>
      client.setQueryData(['pos-shift', shift.outlet_id], shift.status === 'open' ? shift : null),
  })
}

export const useOpenShift = () =>
  useShiftChange((body: { outlet_id: string; opening_float: number }) =>
    request<ShiftOut>('POST', `${POS}/shifts`, body),
  )

export const useCashMovement = (shiftId: string) =>
  useShiftChange((body: { kind: 'in' | 'out'; amount: number; reason: string }) =>
    request<ShiftOut>('POST', `${POS}/shifts/${shiftId}/movements`, body),
  )

export const useCloseShift = (shiftId: string) =>
  useMutation({
    mutationFn: (body: { counted: number; note?: string | null }) =>
      request<ShiftOut>('POST', `${POS}/shifts/${shiftId}/close`, body),
  })

/** After the closing result was read: the till asks for a new shift. */
export function useForgetShift() {
  const client = useQueryClient()
  return (outletId: string) => client.setQueryData(['pos-shift', outletId], null)
}
