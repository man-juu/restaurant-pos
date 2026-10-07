import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type {
  BatchOut,
  MovementPage,
  OpeningIn,
  PostedDocument,
  StockPage,
  ValuationPage,
} from '../../lib/api/types'

const BASE = '/api/v1/inventory'

export const useStock = (outletId: string, lang: string) =>
  useInfiniteQuery({
    queryKey: ['stock', outletId, lang],
    enabled: Boolean(outletId),
    initialPageParam: '',
    queryFn: ({ pageParam }) => {
      const params = new URLSearchParams({ outlet_id: outletId, lang, limit: '100' })
      if (pageParam) params.set('cursor', pageParam)
      return request<StockPage>('GET', `${BASE}/stock?${params}`)
    },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  })

export const useBatches = (outletId: string, itemId: string) =>
  useQuery({
    queryKey: ['batches', outletId, itemId],
    queryFn: () =>
      request<BatchOut[]>('GET', `${BASE}/stock/${itemId}/batches?outlet_id=${outletId}`),
  })

export const useMovements = (outletId: string, itemId: string) =>
  useQuery({
    queryKey: ['movements', outletId, itemId],
    queryFn: () =>
      request<MovementPage>(
        'GET',
        `${BASE}/movements?outlet_id=${outletId}&item_id=${itemId}&limit=20`,
      ),
  })

export const useValuation = (outletId: string, on: string, lang: string) =>
  useQuery({
    queryKey: ['valuation', outletId, on, lang],
    enabled: Boolean(outletId && on),
    queryFn: () =>
      request<ValuationPage>(
        'GET',
        `${BASE}/valuation?outlet_id=${outletId}&on=${on}&lang=${lang}&limit=200`,
      ),
  })

/** Posting changes stock, batches, history and valuation: refresh them all. */
function useLedgerMutation<V>(fn: (vars: V) => Promise<PostedDocument>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all(
        ['stock', 'batches', 'movements', 'valuation', 'costing'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  })
}

export const usePostOpening = () =>
  useLedgerMutation((body: OpeningIn) =>
    // A retried request on a weak connection must not post the stock twice.
    request<PostedDocument>('POST', `${BASE}/opening`, body, {
      'Idempotency-Key': crypto.randomUUID(),
    }),
  )

export const useReverseOpening = () =>
  useLedgerMutation((docId: string) =>
    request<PostedDocument>('POST', `${BASE}/opening/${docId}/reverse`),
  )
