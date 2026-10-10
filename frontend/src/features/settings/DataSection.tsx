import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import { errorMessage } from '../../lib/errors'
import { formatDate, formatNumber, intlLocale } from '../../lib/format'

interface ExportRow {
  id: string
  status: 'queued' | 'ready' | 'failed'
  byte_size: number | null
  created_at: string
  expires_at: string | null
  by_admin: boolean
}

const E = '/api/v1/tenant/exports'

/** FR-TEN-010: a copy of all this business's data, as a ZIP of JSON files. */
export function DataSection() {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const client = useQueryClient()
  const list = useQuery({
    queryKey: ['exports'],
    queryFn: () => request<ExportRow[]>('GET', E),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === 'queued') ? 15_000 : false),
  })
  const ask = useMutation({
    mutationFn: () => request<ExportRow>('POST', E),
    onSuccess: () => client.invalidateQueries({ queryKey: ['exports'] }),
  })
  return (
    <Card className="flex flex-col gap-3">
      <p className="text-sm text-ink-soft">{t('settings.data.help')}</p>
      <Button className="self-start" disabled={ask.isPending} onClick={() => ask.mutate()}>
        {t('settings.data.request')}
      </Button>
      {(ask.error ?? list.error) ? <Alert>{errorMessage(ask.error ?? list.error, t)}</Alert> : null}
      <ul className="flex flex-col gap-2">
        {list.data?.map((r) => (
          <li
            key={r.id}
            className="flex flex-wrap items-center justify-between gap-2 border-b border-line py-1"
          >
            <span className="text-sm">
              {t(`settings.data.status.${r.status}`, {
                date: formatDate(r.created_at.slice(0, 10), locale),
              })}
              {r.by_admin && ` · ${t('settings.data.byAdmin')}`}
              {r.byte_size != null && ` · ${formatNumber(r.byte_size / 1024, locale)} KB`}
            </span>
            {r.status === 'ready' && (
              <a
                className="text-sm font-semibold text-accent underline"
                href={`${E}/${r.id}/download`}
              >
                {t('settings.data.download')}
              </a>
            )}
          </li>
        ))}
      </ul>
    </Card>
  )
}
