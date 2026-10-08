import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { ImportBatch, ImportCheck } from '../../lib/api/types'

const BASE = '/api/v1/catalog'
export const MAX_IMPORT_BYTES = 5 * 1024 * 1024 // matches the server limit

const fileUrl = (path: string, file: File) =>
  `${BASE}/imports/items${path}?file_name=${encodeURIComponent(file.name)}`

export const exportUrl = (format: 'csv' | 'xlsx') => `${BASE}/exports/items?format=${format}`
export const templateUrl = (format: 'csv' | 'xlsx') =>
  `${BASE}/imports/items/template?format=${format}`

export const useImports = () =>
  useQuery({
    queryKey: ['imports'],
    queryFn: () => request<ImportBatch[]>('GET', `${BASE}/imports`),
  })

export const useCheckImport = () =>
  useMutation({
    mutationFn: (file: File) => request<ImportCheck>('POST', fileUrl('/check', file), file),
  })

function useAfterImport() {
  const client = useQueryClient()
  return () =>
    Promise.all([
      client.invalidateQueries({ queryKey: ['imports'] }),
      client.invalidateQueries({ queryKey: ['items'] }),
    ])
}

export function useCommitImport() {
  const refresh = useAfterImport()
  return useMutation({
    mutationFn: (file: File) => request<ImportBatch>('POST', fileUrl('', file), file),
    onSuccess: refresh,
  })
}

export function useRevertImport() {
  const refresh = useAfterImport()
  return useMutation({
    mutationFn: (id: string) => request<ImportBatch>('POST', `${BASE}/imports/${id}/revert`),
    onSuccess: refresh,
  })
}
