import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { OrderIn, OrderOut, ReceiptOut, ReceiveIn } from '../../lib/api/types'

const BASE = '/api/v1/purchasing/orders'

export const useOrders = (outletId: string) =>
  useQuery({
    queryKey: ['orders', outletId],
    queryFn: () => request<OrderOut[]>('GET', `${BASE}?outlet_id=${outletId}`),
  })

export const pdfUrl = (id: string, lang: string) => `${BASE}/${id}/pdf?lang=${lang}`

/** Any order step can change receipts and stock: refresh them all afterwards. */
function useOrderStep<V, R>(fn: (vars: V) => Promise<R>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all(
        ['orders', 'receipts', 'stock'].map((key) => client.invalidateQueries({ queryKey: [key] })),
      ),
  })
}

export const useSaveOrder = () =>
  useOrderStep(({ id, body }: { id?: string; body: OrderIn }) =>
    request<OrderOut>(id ? 'PUT' : 'POST', id ? `${BASE}/${id}` : BASE, body),
  )

export const useOrderAction = () =>
  useOrderStep(
    ({
      id,
      action,
      body,
    }: {
      id: string
      action: 'submit' | 'cancel' | 'decide'
      body?: unknown
    }) => request<OrderOut>('POST', `${BASE}/${id}/${action}`, body),
  )

export const useReceiveOrder = () =>
  useOrderStep(({ id, body, key }: { id: string; body: ReceiveIn; key: string }) =>
    request<ReceiptOut>('POST', `${BASE}/${id}/receipts`, body, { 'Idempotency-Key': key }),
  )
