import { ApiError } from '../../../lib/api/client'
import type { OfflineOrderIn, OfflineSyncOut } from '../../../lib/api/types'

/** FR-SAL-013: orders taken without a connection wait here until the server has them.
 * localStorage survives a closed tab; the client_id makes a second upload harmless. */

export interface QueuedOrder {
  body: OfflineOrderIn
  total: number
}

export interface FailedOrder extends QueuedOrder {
  code: string
}

export interface OfflineQueue {
  pending: QueuedOrder[]
  failed: FailedOrder[]
  problems: OfflineSyncOut[] // synced, but left open for a person to finish
}

// One queue per person: an order is uploaded by whoever took it (the audit trail).
const key = (userId: string) => `pos-offline-queue:${userId}`
const EMPTY: OfflineQueue = { pending: [], failed: [], problems: [] }

export function loadQueue(userId: string): OfflineQueue {
  try {
    const raw = localStorage.getItem(key(userId))
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Partial<OfflineQueue>) } : EMPTY
  } catch {
    return EMPTY
  }
}

export function saveQueue(userId: string, q: OfflineQueue): void {
  try {
    localStorage.setItem(key(userId), JSON.stringify(q))
  } catch {
    // Storage full or blocked: the queue still lives in memory for this page.
  }
}

/** Try again later on a lost connection, a server fault or a busy server; otherwise the
 * server has refused this order for good and a person has to look at it. */
export function isRetryable(err: unknown): boolean {
  if (!(err instanceof ApiError)) return true
  return (
    err.status >= 500 ||
    err.status === 408 ||
    err.status === 429 ||
    err.code === 'offline_sync_busy'
  )
}

/** Upload in order, one at a time; stop at the first retryable failure (still offline). */
export async function drain(
  q: OfflineQueue,
  send: (body: OfflineOrderIn) => Promise<OfflineSyncOut>,
): Promise<OfflineQueue> {
  const next: OfflineQueue = {
    pending: [...q.pending],
    failed: [...q.failed],
    problems: [...q.problems],
  }
  while (next.pending.length > 0) {
    const order = next.pending[0]
    try {
      const out = await send(order.body)
      if (out.problem) next.problems.push(out)
    } catch (err) {
      if (isRetryable(err)) break
      next.failed.push({ ...order, code: err instanceof ApiError ? err.code : 'unknown' })
    }
    next.pending.shift()
  }
  return next
}
