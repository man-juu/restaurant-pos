import { useMutation, useQueryClient } from '@tanstack/react-query'

import { request } from './api/client'
import type { ImportBatch, ImportCheck } from './api/types'

/** One import type: where to check, commit and fetch the template (FR-IMP-001). */
export type ImportKind = {
  base: string // e.g. /api/v1/catalog/imports/items
  invalidates: string[][] // query keys to refresh after an import
}

export const MAX_IMPORT_BYTES = 5 * 1024 * 1024 // matches the server limit

export const IMPORTS = {
  items: {
    base: '/api/v1/catalog/imports/items',
    invalidates: [['items'], ['imports'], ['categories']],
  },
  recipes: { base: '/api/v1/catalog/imports/recipes', invalidates: [['imports'], ['boms']] },
  platform: {
    base: '/api/v1/sales/platform-imports',
    invalidates: [['salesDay'], ['stock'], ['platformImports']],
  },
  opening: { base: '/api/v1/inventory/imports/opening', invalidates: [['stock'], ['openings']] },
} satisfies Record<string, ImportKind>

export const templateUrl = (kind: ImportKind, format: 'csv' | 'xlsx') =>
  `${kind.base}/template?format=${format}`

function fileUrl(kind: ImportKind, path: string, file: File, query: Record<string, string>) {
  const params = new URLSearchParams({ ...query, file_name: file.name })
  return `${kind.base}${path}?${params.toString()}`
}

export const useCheckImport = (kind: ImportKind, query: Record<string, string>) =>
  useMutation({
    mutationFn: (file: File) =>
      request<ImportCheck>('POST', fileUrl(kind, '/check', file, query), file),
  })

export function useCommitImport(kind: ImportKind, query: Record<string, string>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (file: File) => request<ImportBatch>('POST', fileUrl(kind, '', file, query), file),
    onSuccess: () =>
      Promise.all(kind.invalidates.map((key) => client.invalidateQueries({ queryKey: key }))),
  })
}
