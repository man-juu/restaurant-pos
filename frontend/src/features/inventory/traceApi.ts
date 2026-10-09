import { useQuery } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { Trace, TraceBatch } from '../../lib/api/types'

const BASE = '/api/v1/inventory'

export const useLots = (lot: string, lang: string) =>
  useQuery({
    queryKey: ['lots', lot, lang],
    enabled: lot.length > 0,
    queryFn: () =>
      request<TraceBatch[]>(
        'GET',
        `${BASE}/lots?${new URLSearchParams({ lot, lang: lang.slice(0, 2) })}`,
      ),
  })

export const useTrace = (batchId: string | null, lang: string) =>
  useQuery({
    queryKey: ['trace', batchId, lang],
    enabled: Boolean(batchId),
    queryFn: () =>
      request<Trace>('GET', `${BASE}/batches/${batchId}/trace?lang=${lang.slice(0, 2)}`),
  })
