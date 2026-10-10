import { useDeferredValue, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../../components/form'
import { Alert, Button } from '../../../components/ui'
import type { CustomerOut } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { useCreateCustomer, useCustomerSearch } from './arApi'

/** Find a wholesale customer by name or phone, or add a new one by name. */
export function CustomerPick({
  value,
  onPick,
}: {
  value: CustomerOut | null
  onPick: (c: CustomerOut | null) => void
}) {
  const { t } = useTranslation()
  const [q, setQ] = useState('')
  const found = useCustomerSearch(useDeferredValue(q))
  const create = useCreateCustomer()
  if (value)
    return (
      <div className="flex items-center gap-2">
        <p className="font-semibold">{value.name}</p>
        <Button variant="ghost" onClick={() => onPick(null)}>
          {t('ar.form.change')}
        </Button>
      </div>
    )
  return (
    <div className="flex flex-col gap-2">
      <TextInput
        label={t('ar.form.customer')}
        value={q}
        maxLength={60}
        onChange={(e) => setQ(e.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        {found.data?.map((c) => (
          <Button key={c.id} variant="ghost" onClick={() => onPick(c)}>
            {c.name}
          </Button>
        ))}
        {q.trim().length >= 2 && (
          <Button
            variant="ghost"
            disabled={create.isPending}
            onClick={() => create.mutate(q.trim(), { onSuccess: onPick })}
          >
            {t('ar.form.addCustomer', { name: q.trim() })}
          </Button>
        )}
      </div>
      {create.error && <Alert>{errorMessage(create.error, t)}</Alert>}
    </div>
  )
}
