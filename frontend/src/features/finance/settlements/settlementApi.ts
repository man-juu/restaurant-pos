import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../../lib/api/client'
import type { ReconcileOut, SettlementIn, SettlementOut } from '../../../lib/api/types'

const SET = '/api/v1/finance/settlements'

export const useSettlements = (outletId: string) =>
  useQuery({
    queryKey: ['settlements', outletId],
    queryFn: () => request<SettlementOut[]>('GET', `${SET}?outlet_id=${outletId}`),
    enabled: Boolean(outletId),
  })

export type ReconcileArgs = { channelId: string; outletId: string; from: string; to: string }

export const useReconcile = ({ channelId, outletId, from, to }: ReconcileArgs) =>
  useQuery({
    queryKey: ['settlements', 'reconcile', channelId, outletId, from, to],
    queryFn: () =>
      request<ReconcileOut>(
        'GET',
        `${SET}/reconcile?channel_id=${channelId}&outlet_id=${outletId}&from=${from}&to=${to}`,
      ),
    enabled: Boolean(channelId && outletId),
  })

/** A payout moves the bank balance and the books: refresh those too. */
function useRefresh() {
  const client = useQueryClient()
  return () =>
    Promise.all(
      ['settlements', 'fin-accounts', 'gl'].map((key) =>
        client.invalidateQueries({ queryKey: [key] }),
      ),
    )
}

export function useCreateSettlement() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ body, key }: { body: SettlementIn; key: string }) =>
      request<SettlementOut>('POST', SET, body, { 'Idempotency-Key': key }),
    onSuccess: refresh,
  })
}

export function useReverseSettlement() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: string) => request<SettlementOut>('POST', `${SET}/${id}/reverse`),
    onSuccess: refresh,
  })
}
