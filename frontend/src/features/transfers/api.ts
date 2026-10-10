import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type {
  TransferApproveIn,
  TransferOut,
  TransferReceiveIn,
  TransferRequestIn,
} from '../../lib/api/types'

const BASE = '/api/v1/transfers'

export const useTransfers = (outletId: string, lang: string) =>
  useQuery({
    queryKey: ['transfers', outletId, lang],
    queryFn: () =>
      request<TransferOut[]>('GET', `${BASE}?outlet_id=${outletId}&lang=${lang.slice(0, 2)}`),
    enabled: Boolean(outletId),
  })

export const noteUrl = (id: string, lang: string) =>
  `${BASE}/${id}/delivery-note?lang=${lang.slice(0, 2)}`

/** Every step can move stock: refresh transfers and stock afterwards. */
function useStep<V>(fn: (vars: V) => Promise<TransferOut>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all(
        ['transfers', 'stock', 'documents'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  })
}

export const useRequestTransfer = () =>
  useStep(({ body, key }: { body: TransferRequestIn; key: string }) =>
    request<TransferOut>('POST', BASE, body, { 'Idempotency-Key': key }),
  )

type Step =
  | { id: string; action: 'approve'; body: TransferApproveIn }
  | { id: string; action: 'ship'; body: { business_date: string; confirm_negative: boolean } }
  | { id: string; action: 'receive'; body: TransferReceiveIn }
  | { id: string; action: 'cancel'; body?: undefined }

export const useTransferStep = () =>
  useStep((s: Step) => request<TransferOut>('POST', `${BASE}/${s.id}/${s.action}`, s.body))
