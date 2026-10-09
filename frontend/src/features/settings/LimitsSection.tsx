import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Card } from '../../components/ui'
import type { RoleLimitsOut } from '../../lib/api/types'
import { request } from '../../lib/api/client'
import { errorMessage } from '../../lib/errors'
import { bpToPercent, optionalPercentOk, percentToBp } from '../../lib/percent'
import { SaveBar } from './shared'

const DISCOUNT = 'sales.discount.apply'

function useLimits() {
  return useQuery({
    queryKey: ['role-limits'],
    queryFn: () => request<RoleLimitsOut[]>('GET', '/api/v1/role-limits'),
  })
}

/** docs/03 rule 7: the biggest discount each role may give (empty = no limit). */
export function LimitsSection({ canEdit }: { canEdit: boolean }) {
  const { t } = useTranslation()
  const limits = useLimits()
  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-muted">{t('settings.limits.help')}</p>
      {limits.error && <Alert>{errorMessage(limits.error, t)}</Alert>}
      <ul className="flex flex-col gap-3">
        {limits.data
          ?.filter((r) => r.limits.some((l) => l.permission === DISCOUNT))
          .map((role) => (
            <RoleLimit key={role.role_id} role={role} canEdit={canEdit} />
          ))}
      </ul>
    </Card>
  )
}

function RoleLimit({ role, canEdit }: { role: RoleLimitsOut; canEdit: boolean }) {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const current = role.limits.find((l) => l.permission === DISCOUNT)?.value ?? null
  const [text, setText] = useState(current === null ? '' : bpToPercent(current, i18n.language))
  const save = useMutation({
    mutationFn: (value: number | null) =>
      request<RoleLimitsOut[]>('PUT', `/api/v1/role-limits/${role.role_id}`, {
        limits: { [DISCOUNT]: value },
      }),
    onSuccess: (data) => client.setQueryData(['role-limits'], data),
  })
  const valid = optionalPercentOk(text) || text.trim() === '0'
  return (
    <li className="flex flex-wrap items-end gap-3">
      <TextInput
        label={t('settings.limits.discount', { role: role.name })}
        inputMode="decimal"
        value={text}
        disabled={!canEdit}
        invalid={!valid}
        onChange={(e) => setText(e.target.value)}
      />
      {canEdit && (
        <SaveBar
          mutation={save}
          disabled={!valid}
          onSave={() => save.mutate(text.trim() === '' ? null : percentToBp(text))}
        />
      )}
    </li>
  )
}
