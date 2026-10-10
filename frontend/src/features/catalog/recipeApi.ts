import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { BomIn, BomOut, BomSummary, Costing } from '../../lib/api/types'

const BASE = '/api/v1/catalog'

export const useBoms = (itemId: string) =>
  useQuery({
    queryKey: ['boms', itemId],
    queryFn: () => request<BomSummary[]>('GET', `${BASE}/items/${itemId}/boms`),
  })

export const useBom = (bomId: string | undefined, lang: string) =>
  useQuery({
    queryKey: ['bom', bomId, lang],
    enabled: Boolean(bomId),
    queryFn: () => request<BomOut>('GET', `${BASE}/boms/${bomId}?lang=${lang}`),
  })

export const useCosting = (itemId: string, lang: string) =>
  useQuery({
    queryKey: ['costing', itemId, lang],
    queryFn: () => request<Costing>('GET', `${BASE}/items/${itemId}/costing?lang=${lang}`),
  })

/** Every recipe change can change versions, the costing and the open draft. */
export function useRecipeMutations(itemId: string, lang: string) {
  const client = useQueryClient()
  const refresh = () =>
    Promise.all(
      [['boms', itemId], ['costing', itemId], ['bom']].map((queryKey) =>
        client.invalidateQueries({ queryKey }),
      ),
    )
  return {
    save: useMutation({
      mutationFn: ({ bomId, body }: { bomId?: string; body: BomIn }) =>
        bomId
          ? request<BomOut>('PUT', `${BASE}/boms/${bomId}?lang=${lang}`, body)
          : request<BomOut>('POST', `${BASE}/items/${itemId}/boms?lang=${lang}`, body),
      onSuccess: refresh,
    }),
    activate: useMutation({
      mutationFn: ({ bomId, validFrom }: { bomId: string; validFrom: string }) =>
        request<BomSummary>('POST', `${BASE}/boms/${bomId}/activate`, { valid_from: validFrom }),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (bomId: string) => request<void>('DELETE', `${BASE}/boms/${bomId}`),
      onSuccess: refresh,
    }),
  }
}
