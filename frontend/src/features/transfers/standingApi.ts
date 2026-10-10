import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { ChargeRow, StandingIn, StandingOut } from '../../lib/api/types'

const T = '/api/v1/transfers'

export const useStanding = (outletId: string, lang: string) =>
  useQuery({
    queryKey: ['standing', outletId, lang],
    queryFn: () =>
      request<StandingOut[]>('GET', `${T}/standing?outlet_id=${outletId}&lang=${lang.slice(0, 2)}`),
  })

export const useCharges = (from: string, to: string) =>
  useQuery({
    queryKey: ['transfer-charges', from, to],
    queryFn: () => request<ChargeRow[]>('GET', `${T}/reports/charges?from=${from}&to=${to}`),
  })

/** Saving a standing order, or running it now, may create requests: refresh both lists. */
export function useSaveStanding() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: StandingIn }) =>
      request<StandingOut>(id ? 'PUT' : 'POST', id ? `${T}/standing/${id}` : `${T}/standing`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['standing'] }),
  })
}

export function useRunStanding() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => request<{ made: number }>('POST', `${T}/standing/run`),
    onSuccess: () =>
      Promise.all(
        ['standing', 'transfers'].map((key) => client.invalidateQueries({ queryKey: [key] })),
      ),
  })
}
