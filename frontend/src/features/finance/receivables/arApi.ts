import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../../lib/api/client'
import type {
  AgingRow,
  CustomerOut,
  InvoiceIn,
  InvoiceOut,
  ReceiptIn,
} from '../../../lib/api/types'

const INV = '/api/v1/sales/invoices'

export const useInvoices = (outletId: string) =>
  useQuery({
    queryKey: ['invoices', outletId],
    queryFn: () => request<InvoiceOut[]>('GET', `${INV}?outlet_id=${outletId}`),
    enabled: Boolean(outletId),
  })

export const useArAging = (enabled: boolean) =>
  useQuery({
    queryKey: ['invoices', 'aging'],
    queryFn: () => request<AgingRow[]>('GET', `${INV}/aging`),
    enabled,
  })

export const useApAging = (enabled: boolean) =>
  useQuery({
    queryKey: ['payables', 'aging'],
    queryFn: () => request<AgingRow[]>('GET', '/api/v1/purchasing/payables/aging'),
    enabled,
  })

export const useCustomerSearch = (q: string) =>
  useQuery({
    queryKey: ['customers', q],
    queryFn: () => request<CustomerOut[]>('GET', `/api/v1/customers?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length >= 2,
  })

/** Invoice writes move stock and the books: refresh those views too. */
function useRefresh() {
  const client = useQueryClient()
  return () =>
    Promise.all(
      ['invoices', 'stock', 'gl'].map((key) => client.invalidateQueries({ queryKey: [key] })),
    )
}

export function useCreateCustomer() {
  return useMutation({
    mutationFn: (name: string) => request<CustomerOut>('POST', '/api/v1/customers', { name }),
  })
}

/** One idempotency key per form: a retry never invoices twice. */
export function useCreateInvoice() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ body, key }: { body: InvoiceIn; key: string }) =>
      request<InvoiceOut>('POST', INV, body, { 'Idempotency-Key': key }),
    onSuccess: refresh,
  })
}

export function useReceive() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ id, body, key }: { id: string; body: ReceiptIn; key: string }) =>
      request<InvoiceOut>('POST', `${INV}/${id}/payments`, body, { 'Idempotency-Key': key }),
    onSuccess: refresh,
  })
}

export function useVoidInvoice() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: string) => request<InvoiceOut>('POST', `${INV}/${id}/void`),
    onSuccess: refresh,
  })
}
