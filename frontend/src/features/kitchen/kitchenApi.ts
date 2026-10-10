import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { StationOut, TicketOut } from '../../lib/api/types'

const K = '/api/v1/kitchen'

export const useStations = (outletId: string) =>
  useQuery({
    queryKey: ['stations', outletId],
    queryFn: () => request<StationOut[]>('GET', `${K}/stations?outlet_id=${outletId}`),
    enabled: Boolean(outletId),
  })

export const useTickets = (outletId: string, stationId: string, bumped = false) =>
  useQuery({
    queryKey: ['tickets', outletId, stationId, bumped],
    queryFn: () =>
      request<TicketOut[]>(
        'GET',
        `${K}/tickets?outlet_id=${outletId}${stationId ? `&station_id=${stationId}` : ''}&bumped=${bumped}`,
      ),
    enabled: Boolean(outletId),
    refetchInterval: 5_000, // the kitchen screen stays current without a refresh button
  })

export function useTicketStep() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'start' | 'ready' | 'bump' | 'recall' }) =>
      request<void>('POST', `${K}/tickets/${id}/${action}`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['tickets'] }),
  })
}

export function useSaveStation() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      outlet_id: string
      name: string
      category_ids: string[]
      is_default: boolean
    }) => request<StationOut>('POST', `${K}/stations`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['stations'] }),
  })
}
