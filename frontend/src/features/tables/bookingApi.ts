import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { ReservationIn, ReservationOut, Suggestion, WaitOut } from '../../lib/api/types'

const B = '/api/v1/bookings'

export const useReservations = (outletId: string, day: string) =>
  useQuery({
    queryKey: ['reservations', outletId, day],
    queryFn: () =>
      request<ReservationOut[]>('GET', `${B}/reservations?outlet_id=${outletId}&day=${day}`),
    enabled: Boolean(outletId && day),
  })

export const useSuggestions = (
  outletId: string,
  startsAt: string,
  party: number,
  duration?: number,
) =>
  useQuery({
    queryKey: ['suggest', outletId, startsAt, party, duration],
    enabled: Boolean(outletId && startsAt && party > 0),
    queryFn: () => {
      const q = new URLSearchParams({
        outlet_id: outletId,
        starts_at: startsAt,
        party_size: String(party),
      })
      if (duration) q.set('duration_min', String(duration))
      return request<Suggestion[]>('GET', `${B}/suggest?${q}`)
    },
  })

export const useWaitlist = (outletId: string) =>
  useQuery({
    queryKey: ['waitlist', outletId],
    queryFn: () => request<WaitOut[]>('GET', `${B}/waitlist?outlet_id=${outletId}`),
    enabled: Boolean(outletId),
    refetchInterval: 30_000, // the estimate moves as tables free up
  })

/** Any booking change refreshes bookings, the waitlist and the floor. */
export function useBookingAction() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      method,
      path,
      body,
    }: {
      method: 'POST' | 'PUT'
      path: string
      body?: unknown
    }) => request<unknown>(method, `${B}/${path}`, body),
    onSuccess: () =>
      Promise.all(
        ['reservations', 'waitlist', 'tables', 'suggest'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  })
}

export type NewReservation = ReservationIn
