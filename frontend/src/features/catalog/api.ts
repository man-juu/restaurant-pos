import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type {
  CategoryIn,
  CategoryOut,
  ChannelIn,
  ChannelOut,
  ItemIn,
  ItemOut,
  ItemPage,
  ItemUpdate,
  PriceIn,
  PriceOut,
  UnitIn,
  UnitOut,
} from '../../lib/api/types'

const BASE = '/api/v1/catalog'

/** Invalidate a query key after a successful save, so lists show the server's truth. */
function useSave<V, R>(key: readonly unknown[], fn: (vars: V) => Promise<R>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => client.invalidateQueries({ queryKey: key }),
  })
}

export const useUnits = () =>
  useQuery({ queryKey: ['units'], queryFn: () => request<UnitOut[]>('GET', `${BASE}/units`) })

export const useCreateUnit = () =>
  useSave(['units'], (body: UnitIn) => request<UnitOut>('POST', `${BASE}/units`, body))

export const useCategories = () =>
  useQuery({
    queryKey: ['categories'],
    queryFn: () => request<CategoryOut[]>('GET', `${BASE}/categories`),
  })

export const useSaveCategory = () =>
  useSave(['categories'], ({ id, body }: { id?: string; body: CategoryIn }) =>
    id
      ? request<CategoryOut>('PUT', `${BASE}/categories/${id}`, body)
      : request<CategoryOut>('POST', `${BASE}/categories`, body),
  )

export const useChannels = (includeInactive = false) =>
  useQuery({
    queryKey: ['channels', includeInactive],
    queryFn: () =>
      request<ChannelOut[]>('GET', `${BASE}/channels?include_inactive=${includeInactive}`),
  })

export const useSaveChannel = () =>
  useSave(['channels'], ({ id, body }: { id?: string; body: ChannelIn }) =>
    id
      ? request<ChannelOut>('PUT', `${BASE}/channels/${id}`, body)
      : request<ChannelOut>('POST', `${BASE}/channels`, body),
  )

export interface ItemFilter {
  q: string
  type: '' | ItemIn['type']
  lang: string
}

export function useItems({ q, type, lang }: ItemFilter) {
  return useInfiniteQuery({
    queryKey: ['items', q, type, lang],
    initialPageParam: '',
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ lang, include_inactive: 'true', limit: '50' })
      if (q.trim()) params.set('q', q.trim())
      if (type) params.set('type', type)
      if (pageParam) params.set('cursor', pageParam)
      return request<ItemPage>('GET', `${BASE}/items?${params}`)
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })
}

export const useItem = (id: string | undefined, lang: string) =>
  useQuery({
    queryKey: ['item', id, lang],
    enabled: Boolean(id),
    queryFn: () => request<ItemOut>('GET', `${BASE}/items/${id}?lang=${lang}`),
  })

export function useSaveItem(lang: string) {
  const client = useQueryClient()
  return useMutation({
    // A new item gets an idempotency key so a retried request cannot create it twice.
    mutationFn: ({ id, body }: { id?: string; body: ItemIn | ItemUpdate }) =>
      id
        ? request<ItemOut>('PUT', `${BASE}/items/${id}?lang=${lang}`, body)
        : request<ItemOut>('POST', `${BASE}/items?lang=${lang}`, body, {
            'Idempotency-Key': crypto.randomUUID(),
          }),
    onSuccess: (item) => {
      client.setQueryData(['item', item.id, lang], item)
      return client.invalidateQueries({ queryKey: ['items'] })
    },
  })
}

export const usePrices = (itemId: string) =>
  useQuery({
    queryKey: ['prices', itemId],
    queryFn: () => request<PriceOut[]>('GET', `${BASE}/items/${itemId}/prices`),
  })

export const useSetPrice = (itemId: string) =>
  useSave(['prices', itemId], (body: PriceIn) =>
    request<PriceOut>('PUT', `${BASE}/items/${itemId}/prices`, body),
  )

export const useDeletePrice = (itemId: string) =>
  useSave(['prices', itemId], (priceId: string) =>
    request<void>('DELETE', `${BASE}/prices/${priceId}`),
  )
