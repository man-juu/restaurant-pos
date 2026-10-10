import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { request } from '../../lib/api/client'
import type { FloorOut, TableOut, TableSessionOut } from '../../lib/api/types'

const T = '/api/v1/tables'

export const useFloors = (outletId: string) =>
  useQuery({
    queryKey: ['floors', outletId],
    queryFn: () => request<FloorOut[]>('GET', `${T}/floors?outlet_id=${outletId}`),
    enabled: Boolean(outletId),
  })

export const useTables = (outletId: string) =>
  useQuery({
    queryKey: ['tables', outletId],
    queryFn: () => request<TableOut[]>('GET', `${T}?outlet_id=${outletId}`),
    enabled: Boolean(outletId),
    refetchInterval: 20_000, // FR-TBL-004: live occupancy
  })

/** Any change to tables or sessions: refresh the floor (and open orders on the till). */
function useTableChange<V, R>(fn: (vars: V) => Promise<R>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all(
        ['tables', 'floors', 'pos-orders'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  })
}

export const useCreateFloor = () =>
  useTableChange((body: { outlet_id: string; name: string }) =>
    request<FloorOut>('POST', `${T}/floors`, body),
  )

export const useCreateTable = () =>
  useTableChange((body: { floor_id: string; name: string; capacity: number }) =>
    request<TableOut[]>('POST', T, body),
  )

export const useSeat = () =>
  useTableChange(
    ({
      tableId,
      channelId,
      partySize,
    }: {
      tableId: string
      channelId: string
      partySize: number
    }) =>
      request<TableSessionOut>('POST', `${T}/${tableId}/seat`, {
        channel_id: channelId,
        party_size: partySize,
      }),
  )

export const useTableStatus = () =>
  useTableChange(({ tableId, status }: { tableId: string; status: 'available' | 'reserved' }) =>
    request<TableOut[]>('PUT', `${T}/${tableId}/status`, { status }),
  )

type SessionStep =
  | { kind: 'move'; to_table_id: string }
  | { kind: 'merge'; session_id: string }
  | { kind: 'orders' }
  | { kind: 'split'; from_order_id: string; line_ids: string[] }

export const useSessionStep = (sessionId: string) =>
  useTableChange(({ kind, ...body }: SessionStep) =>
    request<TableSessionOut>(
      'POST',
      `${T}/sessions/${sessionId}/${kind}`,
      kind === 'orders' ? undefined : body,
    ),
  )

/** FR-TBL-009: a new spot (grid cell) on the floor plan; everything else stays. */
export const useMoveTable = () =>
  useTableChange(({ table, x, y }: { table: TableOut; x: number; y: number }) =>
    request<TableOut[]>('PUT', `${T}/${table.id}`, {
      floor_id: table.floor_id,
      name: table.name,
      capacity: table.capacity,
      x,
      y,
      is_active: table.is_active,
    }),
  )
