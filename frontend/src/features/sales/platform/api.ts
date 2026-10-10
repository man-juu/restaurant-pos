import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, request } from '../../../lib/api/client'
import type { ColumnMapIn, ColumnMapOut } from '../../../lib/api/types'

const BASE = '/api/v1/sales/platform-imports'

/** The saved layout of this channel's export file; null until someone saves one. */
export const useColumnMap = (channelId: string) =>
  useQuery({
    queryKey: ['platformMap', channelId],
    queryFn: () =>
      request<ColumnMapOut>('GET', `${BASE}/mappings/${channelId}`).catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) return null
        throw err
      }),
    enabled: Boolean(channelId),
  })

export function useSaveColumnMap(channelId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: ColumnMapIn) =>
      request<ColumnMapOut>('PUT', `${BASE}/mappings/${channelId}`, body),
    onSuccess: (saved) => client.setQueryData(['platformMap', channelId], saved),
  })
}

/** The header row of a file, so the mapping can be picked from real column names. */
export const fileColumns = (file: File) =>
  request<string[]>('POST', `${BASE}/columns?file_name=${encodeURIComponent(file.name)}`, file)
