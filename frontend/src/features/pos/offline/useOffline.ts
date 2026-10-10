import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { request } from '../../../lib/api/client'
import type { OfflineOrderIn, OfflinePackOut, OfflineSyncOut } from '../../../lib/api/types'
import { drain, loadQueue, type OfflineQueue, type QueuedOrder, saveQueue } from './queue'

const OFFLINE = '/api/v1/pos/offline'
const EVERY_MS = 30_000

/** Tax, service charge and payment methods for the channel, fetched while online and kept. */
export const useOfflinePack = (channelId: string) =>
  useQuery({
    queryKey: ['pos-offline-pack', channelId],
    queryFn: () => request<OfflinePackOut>('GET', `${OFFLINE}/pack?channel_id=${channelId}`),
    enabled: Boolean(channelId),
    staleTime: 5 * 60_000,
    gcTime: Infinity, // still there when the connection drops
  })

const send = (body: OfflineOrderIn) => request<OfflineSyncOut>('POST', `${OFFLINE}/orders`, body)

/** Whether the browser has a connection, kept up to date. */
function useOnline() {
  const [online, setOnline] = useState(() => navigator.onLine)
  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])
  return online
}

/** The queue for this person and the loop that uploads it: when the connection returns,
 * every 30 seconds, and when the cashier asks. */
export function useOfflineQueue(userId: string) {
  const online = useOnline()
  const client = useQueryClient()
  const [queue, setQueue] = useState<OfflineQueue>(() => loadQueue(userId))
  const [syncing, setSyncing] = useState(false)
  const running = useRef(false)
  const update = useCallback(
    (q: OfflineQueue) => {
      saveQueue(userId, q)
      setQueue(q)
    },
    [userId],
  )
  const sync = useCallback(async () => {
    if (running.current) return
    const before = loadQueue(userId)
    if (before.pending.length === 0) return
    running.current = true
    setSyncing(true)
    try {
      const after = await drain(before, send)
      const seen = new Set(before.pending.map((o) => o.body.client_id))
      const added = loadQueue(userId).pending.filter((o) => !seen.has(o.body.client_id))
      update({ ...after, pending: [...after.pending, ...added] })
      void client.invalidateQueries({ queryKey: ['pos-orders'] })
    } finally {
      running.current = false
      setSyncing(false)
    }
  }, [userId, update, client])
  const add = (order: QueuedOrder) => {
    const q = loadQueue(userId)
    update({ ...q, pending: [...q.pending, order] })
  }
  const clear = () => update({ ...loadQueue(userId), failed: [], problems: [] })
  useEffect(() => {
    if (!online) return
    const first = window.setTimeout(() => void sync(), 0)
    const timer = window.setInterval(() => void sync(), EVERY_MS)
    return () => {
      window.clearTimeout(first)
      window.clearInterval(timer)
    }
  }, [online, sync])
  return { online, queue, syncing, sync, add, clear }
}

export type OfflineState = ReturnType<typeof useOfflineQueue>
