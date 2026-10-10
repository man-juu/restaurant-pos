import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { LevelOut, LevelsIn } from '../../lib/api/types'

const BASE = '/api/v1/inventory/levels'

export const useLevels = (outletId: string, lang: string) =>
  useQuery({
    queryKey: ['levels', outletId, lang],
    queryFn: () =>
      request<LevelOut[]>('GET', `${BASE}?outlet_id=${outletId}&lang=${lang.slice(0, 2)}`),
  })

export function useSaveLevels() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: LevelsIn) => request<LevelOut[]>('PUT', BASE, body),
    onSuccess: () =>
      Promise.all(['levels', 'prep'].map((key) => client.invalidateQueries({ queryKey: [key] }))),
  })
}
