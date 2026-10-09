import { useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { AuditRow } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { todayIso } from '../catalog/labels'

const ACTION = /^[a-z_.]*$/

function query(f: { from: string; to: string; action: string }, cursor?: string) {
  const q = new URLSearchParams({ limit: '50' })
  if (f.from) q.set('from', f.from)
  if (f.to) q.set('to', f.to)
  if (f.action) q.set('action', f.action)
  if (cursor) q.set('cursor', cursor)
  return q
}

/** FR-AUD-004: who did what and when; filter, read and export (never edit). */
export function AuditPage() {
  const { t, i18n } = useTranslation()
  const [from, setFrom] = useState(() => `${todayIso().slice(0, 8)}01`)
  const [to, setTo] = useState(todayIso)
  const [action, setAction] = useState('')
  const f = { from, to, action: ACTION.test(action) ? action : '' }
  const log = useInfiniteQuery({
    queryKey: ['audit', f],
    initialPageParam: '',
    queryFn: ({ pageParam }) =>
      request<{ items: AuditRow[]; next_cursor: string | null }>(
        'GET',
        `/api/v1/audit?${query(f, pageParam || undefined).toString()}`,
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  })
  const rows = log.data?.pages.flatMap((p) => p.items) ?? []
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('audit.title')}</h1>
      <div className="grid gap-3 sm:grid-cols-3">
        <TextInput
          label={t('reports.from')}
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <TextInput
          label={t('reports.to')}
          type="date"
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
        <TextInput
          label={t('audit.action')}
          value={action}
          maxLength={100}
          invalid={!ACTION.test(action)}
          onChange={(e) => setAction(e.target.value.toLowerCase())}
        />
      </div>
      <a
        className="self-start text-sm font-semibold text-accent underline"
        href={`/api/v1/audit/export?${query(f).toString()}&format=xlsx`}
      >
        {t('reports.excel')}
      </a>
      {log.error && <Alert>{errorMessage(log.error, t)}</Alert>}
      {log.isSuccess && rows.length === 0 && <p className="text-ink-soft">{t('reports.empty')}</p>}
      <ul className="flex flex-col gap-2">
        {rows.map((r) => (
          <li key={r.id}>
            <Card className="flex flex-col gap-1 text-sm">
              <span className="font-semibold">{r.action}</span>
              <span className="text-ink-soft">
                {new Date(r.at).toLocaleString(i18n.language)} ·{' '}
                {r.user_name ?? t(`audit.actor.${r.actor_type}`)}
              </span>
            </Card>
          </li>
        ))}
      </ul>
      {log.hasNextPage && (
        <Button
          variant="ghost"
          className="self-start"
          disabled={log.isFetchingNextPage}
          onClick={() => void log.fetchNextPage()}
        >
          {t('audit.more')}
        </Button>
      )}
    </div>
  )
}
