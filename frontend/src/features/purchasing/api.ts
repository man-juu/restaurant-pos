import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type {
  QuickPurchaseIn,
  ReceiptOut,
  UploadRef,
  VendorIn,
  VendorOut,
} from '../../lib/api/types'

const BASE = '/api/v1/purchasing'

export const useVendors = () =>
  useQuery({
    queryKey: ['vendors'],
    queryFn: () => request<VendorOut[]>('GET', `${BASE}/vendors?include_inactive=true`),
  })

export function useSaveVendor() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: VendorIn }) =>
      request<VendorOut>(id ? 'PUT' : 'POST', `${BASE}/vendors${id ? `/${id}` : ''}`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['vendors'] }),
  })
}

export const useReceipts = (outletId: string) =>
  useQuery({
    queryKey: ['receipts', outletId],
    queryFn: () => request<ReceiptOut[]>('GET', `${BASE}/receipts?outlet_id=${outletId}`),
  })

function useRefreshStock() {
  const client = useQueryClient()
  return () =>
    Promise.all(
      ['receipts', 'stock', 'batches', 'movements', 'valuation'].map((key) =>
        client.invalidateQueries({ queryKey: [key] }),
      ),
    )
}

/** One key per purchase: a retry after a dropped connection never receives stock twice. */
export function useQuickPurchase() {
  const refresh = useRefreshStock()
  return useMutation({
    mutationFn: ({ body, key }: { body: QuickPurchaseIn; key: string }) =>
      request<ReceiptOut>('POST', `${BASE}/quick-purchases`, body, { 'Idempotency-Key': key }),
    onSuccess: refresh,
  })
}

export function useReverseReceipt() {
  const refresh = useRefreshStock()
  return useMutation({
    mutationFn: (id: string) => request<ReceiptOut>('POST', `${BASE}/receipts/${id}/reverse`),
    onSuccess: refresh,
  })
}

export const useUploadInvoice = () =>
  useMutation({
    mutationFn: (file: File) => request<UploadRef>('PUT', `${BASE}/attachments`, file),
  })
