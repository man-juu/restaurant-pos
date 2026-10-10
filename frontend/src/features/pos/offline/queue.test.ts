import { describe, expect, it } from 'vitest'

import { ApiError } from '../../../lib/api/client'
import type { OfflineOrderIn, OfflineSyncOut } from '../../../lib/api/types'
import { drain, isRetryable, loadQueue, type OfflineQueue, saveQueue } from './queue'

const order = (id: string) => ({
  body: {
    client_id: id,
    outlet_id: 'o',
    channel_id: 'c',
    taken_at: '',
    lines: [],
  } as unknown as OfflineOrderIn,
  total: 1000,
})
const ok = (id: string, problem: string | null = null): OfflineSyncOut => ({
  client_id: id,
  order_id: 'x',
  number: 'S-1',
  status: problem ? 'open' : 'paid',
  problem,
  skipped_lines: 0,
})
const queue = (...ids: string[]): OfflineQueue => ({
  pending: ids.map(order),
  failed: [],
  problems: [],
})

describe('FR-SAL-013 offline queue', () => {
  it('keeps one queue per person in storage', () => {
    saveQueue('u1', queue('a'))
    expect(loadQueue('u1').pending).toHaveLength(1)
    expect(loadQueue('u2').pending).toHaveLength(0)
  })

  it('retries lost connections, server faults and a busy server only', () => {
    expect(isRetryable(new TypeError('Failed to fetch'))).toBe(true)
    expect(isRetryable(new ApiError(503, 'x', null))).toBe(true)
    expect(isRetryable(new ApiError(409, 'offline_sync_busy', null))).toBe(true)
    expect(isRetryable(new ApiError(422, 'offline_taken_at', null))).toBe(false)
  })

  it('uploads in order, records problems and refusals, stops when offline', async () => {
    const sent: string[] = []
    const send = (b: OfflineOrderIn) => {
      sent.push(b.client_id)
      if (b.client_id === 'b') return Promise.resolve(ok('b', 'lines_skipped'))
      if (b.client_id === 'c') return Promise.reject(new ApiError(403, 'permission_denied', null))
      if (b.client_id === 'd') return Promise.reject(new TypeError('Failed to fetch'))
      return Promise.resolve(ok(b.client_id))
    }
    const out = await drain(queue('a', 'b', 'c', 'd', 'e'), send)
    expect(sent).toEqual(['a', 'b', 'c', 'd'])
    expect(out.pending.map((o) => o.body.client_id)).toEqual(['d', 'e'])
    expect(out.failed.map((o) => o.code)).toEqual(['permission_denied'])
    expect(out.problems.map((p) => p.problem)).toEqual(['lines_skipped'])
  })
})
