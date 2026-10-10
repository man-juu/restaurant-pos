import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, TextInput } from '../../components/form'
import { Alert, Button } from '../../components/ui'
import type { CustomerOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useAddGuest, useGuests } from './api'

/** Find a guest by phone or name, or add one (with their consent, UU PDP). */
export function GuestPicker({ onPick }: { onPick: (c: CustomerOut) => void }) {
  const { t } = useTranslation()
  const [q, setQ] = useState('')
  const found = useGuests(q)
  const rows = found.data ?? []
  return (
    <div className="flex flex-col gap-2">
      <TextInput
        label={t('loyalty.find')}
        inputMode="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {rows.map((c) => (
        <Button key={c.id} variant="ghost" className="justify-start" onClick={() => onPick(c)}>
          {c.name} {c.phone ? `· ${c.phone}` : ''}
        </Button>
      ))}
      {found.isSuccess && rows.length === 0 && <AddGuest phone={q} onAdded={onPick} />}
    </div>
  )
}

function AddGuest({ phone, onAdded }: { phone: string; onAdded: (c: CustomerOut) => void }) {
  const { t } = useTranslation()
  const add = useAddGuest()
  const [name, setName] = useState('')
  const [consent, setConsent] = useState(false)
  const ok = name.trim().length > 0 && /\d{6,}/.test(phone) && consent
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line p-3">
      <p className="text-sm text-ink-soft">{t('loyalty.notFound')}</p>
      <TextInput label={t('loyalty.name')} value={name} onChange={(e) => setName(e.target.value)} />
      <CheckInput label={t('loyalty.consent')} checked={consent} onChange={setConsent} />
      {add.error ? <Alert>{errorMessage(add.error, t)}</Alert> : null}
      <Button
        className="self-start"
        disabled={!ok || add.isPending}
        onClick={() => add.mutate({ name, phone, consent }, { onSuccess: onAdded })}
      >
        {t('loyalty.addGuest')}
      </Button>
    </div>
  )
}
