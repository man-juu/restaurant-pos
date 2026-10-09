import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type {
  ExpenseCategoryOut,
  ExpenseOut,
  MoneyAccountOut,
  ProfitLossOut,
} from '../../lib/api/types'

const F = '/api/v1/finance'

export const useAccounts = () =>
  useQuery({
    queryKey: ['fin-accounts'],
    queryFn: () => request<MoneyAccountOut[]>('GET', `${F}/accounts`),
  })

export const useExpenseCategories = () =>
  useQuery({
    queryKey: ['fin-categories'],
    queryFn: () => request<ExpenseCategoryOut[]>('GET', `${F}/categories`),
  })

export const useExpenses = (outletId: string, from: string, to: string) =>
  useQuery({
    queryKey: ['fin-expenses', outletId, from, to],
    queryFn: () =>
      request<ExpenseOut[]>(
        'GET',
        `${F}/expenses?outlet_id=${outletId}&date_from=${from}&date_to=${to}`,
      ),
    enabled: Boolean(outletId),
  })

export const useProfitLoss = (outletId: string, from: string, to: string) =>
  useQuery({
    queryKey: ['fin-pl', outletId, from, to],
    queryFn: () =>
      request<ProfitLossOut>(
        'GET',
        `${F}/profit-loss?from=${from}&to=${to}${outletId ? `&outlet_id=${outletId}` : ''}`,
      ),
  })

/** Anything that moves money: refresh balances, expenses and the P&L. */
export function useFinanceChange<V, R>(fn: (vars: V) => Promise<R>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all(
        ['fin-accounts', 'fin-categories', 'fin-expenses', 'fin-pl'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  })
}

export const post = <R>(path: string, body: unknown, key?: string) =>
  request<R>('POST', `${F}${path}`, body, key ? { 'Idempotency-Key': key } : {})
