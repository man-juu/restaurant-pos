import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type {
  BookedOut,
  BookingLinkOut,
  BookingPage,
  NewBookingLinkOut,
  OnlineIn,
  ReminderOut,
} from '../../lib/api/types'

const P = '/api/v1/public/booking'
const B = '/api/v1/bookings'

/** FR-TBL-010: the public page. The token in the address is the only key. */
export const useBookingPage = (token: string) =>
  useQuery({
    queryKey: ['public-booking', token],
    queryFn: () => request<BookingPage>('GET', `${P}/${encodeURIComponent(token)}`),
    retry: false,
  })

export const useSlots = (token: string, day: string, party: number) =>
  useQuery({
    queryKey: ['public-booking', token, day, party],
    queryFn: () =>
      request<string[]>(
        'GET',
        `${P}/${encodeURIComponent(token)}/slots?day=${day}&party_size=${party}`,
      ),
    enabled: Boolean(day && party > 0),
  })

export const useBookOnline = (token: string) =>
  useMutation({
    mutationFn: ({ body, key }: { body: OnlineIn; key: string }) =>
      request<BookedOut>('POST', `${P}/${encodeURIComponent(token)}`, body, {
        'Idempotency-Key': key,
      }),
  })

export const useBookingLinks = (outletId: string) =>
  useQuery({
    queryKey: ['booking-links', outletId],
    queryFn: () => request<BookingLinkOut[]>('GET', `${B}/links?outlet_id=${outletId}`),
    enabled: Boolean(outletId),
  })

export function useLinkAction() {
  const client = useQueryClient()
  const onSuccess = () => client.invalidateQueries({ queryKey: ['booking-links'] })
  return {
    create: useMutation({
      mutationFn: (outletId: string) =>
        request<NewBookingLinkOut>('POST', `${B}/links`, { outlet_id: outletId }),
      onSuccess,
    }),
    disable: useMutation({
      mutationFn: (id: string) => request<BookingLinkOut>('POST', `${B}/links/${id}/disable`),
      onSuccess,
    }),
  }
}

export function useRemind() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => request<ReminderOut>('POST', `${B}/reservations/${id}/remind`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['reservations'] }),
  })
}

/** WhatsApp click-to-chat with the text filled in; staff press send themselves. */
export const whatsappUrl = (phone: string, message: string) =>
  `https://wa.me/${phone.replace(/\D/g, '')}?text=${encodeURIComponent(message)}`

export const bookingUrl = (token: string) => `${window.location.origin}/book/${token}`
