import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput } from '../../components/form'
import { Alert } from '../../components/ui'
import { request } from '../../lib/api/client'
import { errorMessage } from '../../lib/errors'
import { useOutlets } from '../../lib/session'

/** FR-TEN-011: sold out at one outlet only (the menu itself stays shared). */
export function OutletAvailability({ itemId, canToggle }: { itemId: string; canToggle: boolean }) {
  const { t } = useTranslation()
  const outlets = (useOutlets().data ?? []).filter((o) => o.is_active)
  const [off, setOff] = useState<string[]>([])
  const toggle = useMutation({
    mutationFn: ({ outletId, available }: { outletId: string; available: boolean }) =>
      request<void>('PUT', `/api/v1/catalog/items/${itemId}/outlets/${outletId}/availability`, {
        is_available: available,
      }),
    onSuccess: (_, v) =>
      setOff(v.available ? off.filter((o) => o !== v.outletId) : [...off, v.outletId]),
  })
  if (outlets.length < 2) return null
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="text-sm font-semibold">{t('catalog.modifiers.perOutlet')}</legend>
      {outlets.map((o) => (
        <CheckInput
          key={o.id}
          label={o.name}
          checked={!off.includes(o.id)}
          disabled={!canToggle || toggle.isPending}
          onChange={(available) => toggle.mutate({ outletId: o.id, available })}
        />
      ))}
      {toggle.error ? <Alert>{errorMessage(toggle.error, t)}</Alert> : null}
    </fieldset>
  )
}
