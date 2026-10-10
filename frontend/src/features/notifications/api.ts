import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { NotificationOut } from '../../lib/api/types'

const BASE = '/api/v1/notifications'
const POLL_MS = 60_000 // alerts are raised by a job every few minutes

export const useUnread = () =>
  useQuery({
    queryKey: ['notifications', 'unread'],
    queryFn: () => request<{ unread: number }>('GET', `${BASE}/unread-count`),
    refetchInterval: POLL_MS,
  })

export const useNotifications = () =>
  useQuery({
    queryKey: ['notifications', 'list'],
    queryFn: () => request<NotificationOut[]>('GET', BASE),
  })

export function useMarkRead() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id?: string) =>
      request<void>('POST', id ? `${BASE}/${id}/read` : `${BASE}/read-all`),
    onSuccess: () => client.invalidateQueries({ queryKey: ['notifications'] }),
  })
}
