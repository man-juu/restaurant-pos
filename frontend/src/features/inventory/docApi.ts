import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { AdjustmentIn, CountedIn, CountIn, StockDocument, WasteIn } from '../../lib/api/types'

const BASE = '/api/v1/inventory'
export type DocPath = 'waste' | 'adjustments' | 'counts'

export const useDocuments = (kind: DocPath, outletId: string) =>
  useQuery({
    queryKey: ['documents', kind, outletId],
    queryFn: () =>
      request<StockDocument[]>('GET', `${BASE}/documents/${kind}?outlet_id=${outletId}`),
  })

export const useDocument = (kind: DocPath, id: string | undefined, lang: string) =>
  useQuery({
    queryKey: ['document', kind, id, lang],
    enabled: Boolean(id),
    queryFn: () => request<StockDocument>('GET', `${BASE}/documents/${kind}/${id}?lang=${lang}`),
  })

/** Any document step can change stock, so every stock view is refreshed afterwards. */
export function useDocMutation<V>(fn: (vars: V) => Promise<StockDocument>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all(
        ['documents', 'document', 'stock', 'batches', 'movements', 'valuation'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  })
}

const post = (path: string, body?: unknown, idempotent = false) =>
  request<StockDocument>(
    'POST',
    `${BASE}/${path}`,
    body,
    idempotent ? { 'Idempotency-Key': crypto.randomUUID() } : {},
  )

export const usePostWaste = () => useDocMutation((body: WasteIn) => post('waste', body, true))
export const useReverseWaste = () => useDocMutation((id: string) => post(`waste/${id}/reverse`))

/** Create the adjustment and submit it in one go: a draft nobody submits helps no one. */
export const useSubmitNewAdjustment = () =>
  useDocMutation(async (body: AdjustmentIn) => {
    const draft = await post('adjustments', body)
    return post(`adjustments/${draft.id}/submit`)
  })

export const useDecide = (kind: 'adjustments' | 'counts') =>
  useDocMutation(({ id, approve }: { id: string; approve: boolean }) =>
    post(`${kind}/${id}/${approve ? 'approve' : 'reject'}`),
  )

export const useStartCount = () => useDocMutation((body: CountIn) => post('counts', body))

export const useSaveCounted = () =>
  useDocMutation(({ id, body }: { id: string; body: CountedIn }) =>
    request<StockDocument>('PUT', `${BASE}/counts/${id}/lines`, body),
  )

export const useSubmitCount = () => useDocMutation((id: string) => post(`counts/${id}/submit`))
