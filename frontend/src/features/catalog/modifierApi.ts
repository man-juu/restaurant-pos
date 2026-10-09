import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { ModifierGroupIn, ModifierGroupOut } from '../../lib/api/types'

const BASE = '/api/v1/catalog'

export const useModifierGroups = () =>
  useQuery({
    queryKey: ['modifier-groups'],
    queryFn: () => request<ModifierGroupOut[]>('GET', `${BASE}/modifier-groups`),
  })

export function useSaveModifierGroup() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: ModifierGroupIn }) =>
      id
        ? request<ModifierGroupOut>('PUT', `${BASE}/modifier-groups/${id}`, body)
        : request<ModifierGroupOut>('POST', `${BASE}/modifier-groups`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['modifier-groups'] }),
  })
}

export const useItemModifierGroups = (itemId: string) =>
  useQuery({
    queryKey: ['item-modifier-groups', itemId],
    queryFn: () => request<ModifierGroupOut[]>('GET', `${BASE}/items/${itemId}/modifier-groups`),
  })

export function useSetItemModifierGroups(itemId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (groupIds: string[]) =>
      request<ModifierGroupOut[]>('PUT', `${BASE}/items/${itemId}/modifier-groups`, {
        group_ids: groupIds,
      }),
    onSuccess: (data) => client.setQueryData(['item-modifier-groups', itemId], data),
  })
}

export function useSetAvailability(itemId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (available: boolean) =>
      request<void>('PUT', `${BASE}/items/${itemId}/availability`, { is_available: available }),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ['items'] }),
        client.invalidateQueries({ queryKey: ['item', itemId] }),
      ]),
  })
}
