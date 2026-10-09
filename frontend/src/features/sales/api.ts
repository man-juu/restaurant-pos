import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { DayEntryIn, DayOut, EffectivePrice, ItemPage } from '../../lib/api/types'

const BASE = '/api/v1/sales/days'
const lng = (lang: string) => lang.slice(0, 2)

export const useDay = (outletId: string, on: string, lang: string) =>
  useQuery({
    queryKey: ['salesDay', outletId, on, lang],
    queryFn: () => request<DayOut>('GET', `${BASE}/${outletId}/${on}?lang=${lng(lang)}`),
    enabled: Boolean(outletId && on),
  })

/** Menu items with a list price on the channel that day: the rows of the entry grid. */
export function usePriceList(channelId: string, on: string, lang: string) {
  return useQuery({
    queryKey: ['priceList', channelId, on, lang],
    enabled: Boolean(channelId && on),
    queryFn: async () => {
      const [prices, items] = await Promise.all([
        request<{ items: EffectivePrice[] }>(
          'GET',
          `/api/v1/catalog/prices?channel_id=${channelId}&on=${on}&limit=200`,
        ),
        request<ItemPage>('GET', `/api/v1/catalog/items?type=menu&limit=200&lang=${lng(lang)}`),
      ])
      const names = new Map(items.items.map((i) => [i.id, i.name]))
      return prices.items
        .filter((p) => names.has(p.item_id))
        .map((p) => ({ item_id: p.item_id, name: names.get(p.item_id) ?? '', price: p.price }))
        .sort((a, b) => a.name.localeCompare(b.name))
    },
  })
}

function useDayStep<V>(fn: (vars: V) => Promise<DayOut>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all(
        ['salesDay', 'stock'].map((key) => client.invalidateQueries({ queryKey: [key] })),
      ),
  })
}

export const useEnterDay = () =>
  useDayStep(({ body, key }: { body: DayEntryIn; key: string }) =>
    request<DayOut>('POST', `${BASE}/entries`, body, { 'Idempotency-Key': key }),
  )

export const useLockDay = () =>
  useDayStep(({ outletId, on, lock }: { outletId: string; on: string; lock: boolean }) =>
    request<DayOut>('POST', `${BASE}/${outletId}/${on}/${lock ? 'lock' : 'reopen'}`),
  )
