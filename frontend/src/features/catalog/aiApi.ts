import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { AiUsage, GenerateOut, UploadRef } from '../../lib/api/types'

const BASE = '/api/v1/catalog'

/** FR-CAT-013: today's remaining free AI images for this business (server-decided). */
export const useAiUsage = () =>
  useQuery({
    queryKey: ['ai-usage'],
    queryFn: () => request<AiUsage>('GET', `${BASE}/ai-images/usage`),
  })

export function useGenerateImage() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (prompt: string) => request<GenerateOut>('POST', `${BASE}/ai-images`, { prompt }),
    onSuccess: (out) => client.setQueryData(['ai-usage'], out.usage),
    onError: () => client.invalidateQueries({ queryKey: ['ai-usage'] }),
  })
}

export function useAcceptImage(itemId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (uploadId: string) =>
      request<UploadRef>('PUT', `${BASE}/items/${itemId}/photo/${uploadId}`),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: ['item', itemId] }),
        client.invalidateQueries({ queryKey: ['items'] }),
      ]),
  })
}
