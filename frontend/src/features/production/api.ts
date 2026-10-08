import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { ProductionCompleteIn, ProductionOut, ProductionPlanIn } from '../../lib/api/types'

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
        ['production', 'stock'].map((key) => client.invalidateQueries({ queryKey: [key] })),
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
