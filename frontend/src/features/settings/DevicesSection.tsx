import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card, StateBadge } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { Capabilities, DeviceOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useOutlets } from '../../lib/session'

const KEY = ['devices']

/** FR-IDN-004: shared tills and tablets where staff may sign in with a PIN. */
export function DevicesSection() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const allowed = Boolean(caps?.permissions.includes('tenant.device.manage'))
  const client = useQueryClient()
  const list = useQuery({
    queryKey: KEY,
    queryFn: () => request<DeviceOut[]>('GET', '/api/v1/devices'),
    enabled: allowed,
  })
  const revoke = useMutation({
    mutationFn: (id: string) => request<void>('DELETE', `/api/v1/devices/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
  if (!allowed) return <p className="text-sm text-ink-soft">{t('devices.notAllowed')}</p>
  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-muted">{t('devices.help')}</p>
      <RegisterThis />
      {list.error || revoke.error ? (
        <Alert>{errorMessage(list.error ?? revoke.error, t)}</Alert>
      ) : null}
      <ul className="flex flex-col gap-2">
        {list.data?.map((d) => (
          <li key={d.id} className="flex flex-wrap items-center justify-between gap-2">
            <b>{d.name}</b>
            {d.revoked_at ? (
              <StateBadge state="read_only" label={t('devices.revoked')} />
            ) : (
              <Button variant="ghost" onClick={() => revoke.mutate(d.id)}>
                {t('devices.revoke')}
              </Button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  )
}

function RegisterThis() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const outlets = (useOutlets().data ?? []).filter((o) => o.is_active)
  const [name, setName] = useState('')
  const [outletId, setOutlet] = useState('')
  const register = useMutation({
    mutationFn: () =>
      request<DeviceOut>('POST', '/api/v1/devices', {
        name: name.trim(),
        outlet_id: outletId || null,
      }),
    onSuccess: () =>
      Promise.all([KEY, ['this-device']].map((queryKey) => client.invalidateQueries({ queryKey }))),
  })
  return (
    <div className="grid gap-2 sm:grid-cols-3 sm:items-end">
      <TextInput
        label={t('devices.name')}
        value={name}
        maxLength={80}
        onChange={(e) => setName(e.target.value)}
      />
      <SelectInput
        label={t('devices.outlet')}
        value={outletId}
        onChange={(e) => setOutlet(e.target.value)}
      >
        <option value="">{t('devices.anyOutlet')}</option>
        {outlets.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </SelectInput>
      <Button disabled={!name.trim() || register.isPending} onClick={() => register.mutate()}>
        {t('devices.registerThis')}
      </Button>
      {register.error ? <Alert>{errorMessage(register.error, t)}</Alert> : null}
      {register.isSuccess && (
        <p role="status" className="text-sm text-good sm:col-span-3">
          {t('devices.registered')}
        </p>
      )}
    </div>
  )
}
