import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type {
  PrepRow,
  ProductionCompleteIn,
  ProductionOut,
  ProductionPlanIn,
} from '../../lib/api/types'

const BASE = '/api/v1/production/orders'

export const useProduction = (outletId: string, lang: string) =>
  useQuery({
    queryKey: ['production', outletId, lang],
    queryFn: () =>
      request<ProductionOut[]>('GET', `${BASE}?outlet_id=${outletId}&lang=${lang.slice(0, 2)}`),
    enabled: Boolean(outletId),
  })

/** Every step can move stock: refresh production and stock afterwards. */
function useStep<V>(fn: (vars: V) => Promise<ProductionOut>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all(
        ['production', 'stock', 'prep'].map((key) => client.invalidateQueries({ queryKey: [key] })),
      ),
  })
}

export const usePlan = () =>
  useStep(({ body, key }: { body: ProductionPlanIn; key: string }) =>
    request<ProductionOut>('POST', BASE, body, { 'Idempotency-Key': key }),
  )

export const useComplete = () =>
  useStep(({ id, body }: { id: string; body: ProductionCompleteIn }) =>
    request<ProductionOut>('POST', `${BASE}/${id}/complete`, body),
  )

export const useProductionAction = () =>
  useStep(({ id, action }: { id: string; action: 'cancel' | 'reverse' }) =>
    request<ProductionOut>('POST', `${BASE}/${id}/${action}`),
  )

export const usePrepList = (outletId: string, on: string, lang: string) =>
  useQuery({
    queryKey: ['prep', outletId, on, lang],
    queryFn: () =>
      request<PrepRow[]>(
        'GET',
        `/api/v1/production/prep-list?outlet_id=${outletId}&on=${on}&lang=${lang.slice(0, 2)}`,
      ),
    enabled: Boolean(outletId),
  })

export const prepPdfUrl = (outletId: string, on: string, lang: string) =>
  `/api/v1/production/prep-list/pdf?outlet_id=${outletId}&on=${on}&lang=${lang.slice(0, 2)}`

export const labelsUrl = (id: string, copies: number, lang: string) =>
  `${BASE}/${id}/labels?copies=${copies}&lang=${lang.slice(0, 2)}`
