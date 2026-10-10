import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import { errorMessage } from '../../lib/errors'

interface Restore {
  id: string
  restore_to: string
  reason: string
  status: string
}

/** FR-ADM-007: start a data export for the owner, and record a restore request. */
export function TenantOps({ tenantId }: { tenantId: string }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const base = `/admin-api/tenants/${tenantId}`
  const restores = useQuery({
    queryKey: ['admin-restores', tenantId],
    queryFn: () => request<Restore[]>('GET', `${base}/restore-requests`),
  })
  const exportNow = useMutation({ mutationFn: () => request('POST', `${base}/exports`) })
  const [when, setWhen] = useState('')
  const [reason, setReason] = useState('')
  const restore = useMutation({
    mutationFn: () =>
      request('POST', `${base}/restore-requests`, {
        restore_to: new Date(when).toISOString(),
        reason: reason.trim(),
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: ['admin-restores', tenantId] }),
  })
  const error = exportNow.error ?? restore.error ?? restores.error
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-lg font-bold">{t('admin.ops.title')}</h2>
      <Button
        className="self-start"
        variant="ghost"
        disabled={exportNow.isPending}
        onClick={() => exportNow.mutate()}
      >
        {t('admin.ops.export')}
      </Button>
      {exportNow.isSuccess && <p className="text-sm text-good">{t('admin.ops.exportQueued')}</p>}
      <TextInput
        label={t('admin.ops.restoreTo')}
        type="datetime-local"
        value={when}
        onChange={(e) => setWhen(e.target.value)}
      />
      <TextInput
        label={t('admin.ops.reason')}
        value={reason}
        maxLength={500}
        onChange={(e) => setReason(e.target.value)}
      />
      <Button
        className="self-start"
        disabled={!when || reason.trim().length < 10 || restore.isPending}
        onClick={() => restore.mutate()}
      >
        {t('admin.ops.restore')}
      </Button>
      {error ? <Alert>{errorMessage(error, t)}</Alert> : null}
      <ul className="text-sm">
        {restores.data?.map((r) => (
          <li
            key={r.id}
          >{`${new Date(r.restore_to).toLocaleString()} · ${r.status} · ${r.reason}`}</li>
        ))}
      </ul>
    </Card>
  )
}
