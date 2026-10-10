import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { ImportBatch } from '../../lib/api/types'

const BASE = '/api/v1/catalog'

export const exportUrl = (format: 'csv' | 'xlsx') => `${BASE}/exports/items?format=${format}`

export const useImports = () =>
  useQuery({
    queryKey: ['imports'],
    queryFn: () => request<ImportBatch[]>('GET', `${BASE}/imports`),
  })

export function useRevertImport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => request<ImportBatch>('POST', `${BASE}/imports/${id}/revert`),
    onSuccess: () =>
      Promise.all(
        [['imports'], ['items'], ['boms']].map((key) =>
          client.invalidateQueries({ queryKey: key }),
        ),
      ),
  })
}
