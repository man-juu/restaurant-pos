import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Alert, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import { errorMessage } from '../../lib/errors'
import { formatNumber, intlLocale } from '../../lib/format'

interface Usage {
  outlets: number
  active_users: number
  last_activity: string | null
  storage_bytes: number
  job_failures_7d: number
  flags: Record<string, boolean>
}

const MB = 1024 * 1024

/** FR-ADM-004, 006: one business's usage, and its feature flags (super admins change them). */
export function TenantUsage({ tenantId }: { tenantId: string }) {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const locale = intlLocale(i18n.language)
  const usage = useQuery({
    queryKey: ['admin-usage', tenantId],
    queryFn: () => request<Usage>('GET', `/admin-api/tenants/${tenantId}/usage`),
  })
  const setFlag = useMutation({
    mutationFn: (flags: Record<string, boolean>) =>
      request('PUT', `/admin-api/tenants/${tenantId}/flags`, { flags }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['admin-usage', tenantId] }),
  })
  const u = usage.data
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-lg font-bold">{t('admin.usage.title')}</h2>
      {usage.error && <Alert>{errorMessage(usage.error, t)}</Alert>}
      {u && (
        <ul className="grid gap-1 text-sm sm:grid-cols-2">
          <li>{t('admin.usage.outlets', { count: u.outlets })}</li>
          <li>{t('admin.usage.users', { count: u.active_users })}</li>
          <li>
            {t('admin.usage.last', {
              at: u.last_activity ? new Date(u.last_activity).toLocaleString(i18n.language) : '–',
            })}
          </li>
          <li>{t('admin.usage.storage', { mb: formatNumber(u.storage_bytes / MB, locale) })}</li>
          <li className={u.job_failures_7d ? 'text-danger' : ''}>
            {t('admin.usage.failures', { count: u.job_failures_7d })}
          </li>
        </ul>
      )}
      {setFlag.error ? <Alert>{errorMessage(setFlag.error, t)}</Alert> : null}
      {u &&
        Object.entries(u.flags).map(([flag, on]) => (
          <label key={flag} className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="h-5 w-5 accent-[var(--accent)]"
              checked={on}
              onChange={(e) => setFlag.mutate({ [flag]: e.target.checked })}
            />
            {t(`admin.flags.${flag}`)}
          </label>
        ))}
    </Card>
  )
}
