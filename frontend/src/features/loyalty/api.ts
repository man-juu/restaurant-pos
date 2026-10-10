import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { CustomerOut, EarnOut, LoyaltyBalance, VoucherOut } from '../../lib/api/types'

const L = '/api/v1/loyalty'

export const useGuests = (q: string) =>
  useQuery({
    queryKey: ['customers', q],
    queryFn: () => request<CustomerOut[]>('GET', `/api/v1/customers?q=${encodeURIComponent(q)}`),
    enabled: q.trim().length >= 3,
  })

export const useBalance = (customerId: string | null) =>
  useQuery({
    queryKey: ['loyalty', customerId],
    queryFn: () => request<LoyaltyBalance>('GET', `${L}/customers/${customerId}`),
    enabled: Boolean(customerId),
  })

export const useVouchers = (enabled: boolean) =>
  useQuery({
    queryKey: ['loyalty', 'vouchers'],
    queryFn: () => request<VoucherOut[]>('GET', `${L}/vouchers`),
    enabled,
  })

function useRefresh() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: ['loyalty'] })
}

export function useEarn() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (body: { document_id: string; customer_id: string }) =>
      request<EarnOut>('POST', `${L}/earn`, body),
    onSuccess: refresh,
  })
}

/** One idempotency key per form: a retry never spends the points twice. */
export function useRedeem() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ body, key }: { body: { customer_id: string; points: number }; key: string }) =>
      request<VoucherOut>('POST', `${L}/redeem`, body, { 'Idempotency-Key': key }),
    onSuccess: refresh,
  })
}

export function useIssue() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: ({ body, key }: { body: { amount: number; note?: string }; key: string }) =>
      request<VoucherOut>('POST', `${L}/vouchers`, body, { 'Idempotency-Key': key }),
    onSuccess: refresh,
  })
}

export function useVoid() {
  const refresh = useRefresh()
  return useMutation({
    mutationFn: (id: string) => request<VoucherOut>('POST', `${L}/vouchers/${id}/void`),
    onSuccess: refresh,
  })
}

export function useAddGuest() {
  return useMutation({
    mutationFn: (body: { name: string; phone: string; consent: boolean }) =>
      request<CustomerOut>('POST', '/api/v1/customers', body),
  })
}
