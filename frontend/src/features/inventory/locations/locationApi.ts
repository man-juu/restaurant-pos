import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../../lib/api/client'
import type { HomeOut, LocationOut, ScanOut } from '../../../lib/api/types'

const INV = '/api/v1/inventory'

export const useLocations = (outletId: string) =>
  useQuery({
    queryKey: ['locations', outletId],
    queryFn: () => request<LocationOut[]>('GET', `${INV}/locations?outlet_id=${outletId}`),
    enabled: Boolean(outletId),
  })

export const useHomes = (outletId: string, lang: string) =>
  useQuery({
    queryKey: ['locations', 'homes', outletId, lang],
    queryFn: () =>
      request<HomeOut[]>(
        'GET',
        `${INV}/locations/homes?outlet_id=${outletId}&lang=${lang.slice(0, 2)}`,
      ),
    enabled: Boolean(outletId),
  })

/** FR-INV-019: what a scanned or typed code names (a batch or an item). */
export const scanCode = (outletId: string, code: string, lang: string) =>
  request<ScanOut>(
    'GET',
    `${INV}/scan?outlet_id=${outletId}&code=${encodeURIComponent(code)}&lang=${lang.slice(0, 2)}`,
  )

export const labelsUrl = (
  outletId: string,
  lang: string,
  ids: { batch?: string[]; item?: string[] },
) => {
  const q = new URLSearchParams({ outlet_id: outletId, lang: lang.slice(0, 2) })
  for (const b of ids.batch ?? []) q.append('batch_id', b)
  for (const i of ids.item ?? []) q.append('item_id', i)
  return `${INV}/labels?${q.toString()}`
}

/** Location writes: `path` is relative to the inventory API. */
export function useLocationAction() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      method,
      path,
      body,
    }: {
      method: 'POST' | 'PUT' | 'DELETE'
      path: string
      body?: unknown
    }) => request<unknown>(method, `${INV}/${path}`, body),
    onSuccess: () => client.invalidateQueries({ queryKey: ['locations'] }),
  })
}
