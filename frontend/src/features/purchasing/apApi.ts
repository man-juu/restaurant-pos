import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type {
  BaseLine,
  PayableRow,
  PaymentIn,
  VendorBillIn,
  VendorBillOut,
  VendorReturnIn,
  VendorReturnOut,
} from '../../lib/api/types'

const BASE = '/api/v1/purchasing'
const KEYS = ['returns', 'bills', 'payables', 'stock', 'receipts', 'batches', 'valuation']

function useRefresh() {
  const client = useQueryClient()
  return () => Promise.all(KEYS.map((key) => client.invalidateQueries({ queryKey: [key] })))
}

export const useReturns = (outletId: string) =>
  useQuery({
    queryKey: ['returns', outletId],
    queryFn: () => request<VendorReturnOut[]>('GET', `${BASE}/returns?outlet_id=${outletId}`),
  })

export const useBills = (outletId: string) =>
  useQuery({
    queryKey: ['bills', outletId],
    queryFn: () => request<VendorBillOut[]>('GET', `${BASE}/bills?outlet_id=${outletId}`),
  })

export const usePayables = () =>
  useQuery({
    queryKey: ['payables'],
    queryFn: () => request<PayableRow[]>('GET', `${BASE}/payables`),
  })

export const fetchReceiptLines = (receiptId: string, lang: string) =>
  request<BaseLine[]>('GET', `${BASE}/returns/receipt-lines/${receiptId}?lang=${lang.slice(0, 2)}`)

/** Create calls carry one idempotency key per form: a retry never posts twice. */
export function useCreateReturn() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ body, key }: { body: VendorReturnIn; key: string }) =>
      request<VendorReturnOut>('POST', `${BASE}/returns`, body, { 'Idempotency-Key': key }),
    onSuccess: refresh,
  })
}

export function useCreateBill() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ body, key }: { body: VendorBillIn; key: string }) =>
      request<VendorBillOut>('POST', `${BASE}/bills`, body, { 'Idempotency-Key': key }),
    onSuccess: refresh,
  })
}

export function usePayBill() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ id, body, key }: { id: string; body: PaymentIn; key: string }) =>
      request<VendorBillOut>('POST', `${BASE}/bills/${id}/payments`, body, {
        'Idempotency-Key': key,
      }),
    onSuccess: refresh,
  })
}

/** Small actions: `path` is relative to purchasing, e.g. `bills/<id>/void`. */
export function useApAction() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) =>
      request<unknown>('POST', `${BASE}/${path}`, body),
    onSuccess: refresh,
  })
}
