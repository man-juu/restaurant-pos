import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { BookedOut, BookingPage } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useBookOnline, useSlots } from './api'

const isoDay = (d: Date) => d.toLocaleDateString('sv') // YYYY-MM-DD in local time
const addDays = (n: number) => isoDay(new Date(Date.now() + n * 86_400_000))

type Props = { token: string; page: BookingPage; onDone: (b: BookedOut) => void }

/** Day and party first; then only times that still have a table; then name and phone. */
export function BookForm({ token, page, onDone }: Props) {
  const { t } = useTranslation()
  const [day, setDay] = useState(() => addDays(0))
  const [party, setParty] = useState(2)
  const [slot, setSlot] = useState('')
  const [guest, setGuest] = useState({ name: '', phone: '', notes: '' })
  const [consent, setConsent] = useState(false)
  const [key] = useState(() => crypto.randomUUID())
  const book = useBookOnline(token)
  const ready = slot && guest.name.trim() && guest.phone.trim().length >= 8 && consent
  const submit = () =>
    book.mutate(
      {
        key,
        body: {
          name: guest.name,
          phone: guest.phone,
          party_size: party,
          starts_at: slot,
          notes: guest.notes || null,
          consent: true,
        },
      },
      { onSuccess: onDone },
    )
  return (
    <Card className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-3">
        <TextInput
          label={t('book.day')}
          type="date"
          min={addDays(0)}
          max={addDays(page.days_ahead)}
          value={day}
          onChange={(e) => (setDay(e.target.value), setSlot(''))}
        />
        <TextInput
          label={t('book.party')}
          type="number"
          min={1}
          max={page.max_party}
          value={party}
          onChange={(e) => (setParty(Number(e.target.value) || 1), setSlot(''))}
        />
      </div>
      <Times
        token={token}
        tz={page.timezone}
        day={day}
        party={party}
        value={slot}
        onPick={setSlot}
      />
      <TextInput
        label={t('book.name')}
        autoComplete="name"
        value={guest.name}
        onChange={(e) => setGuest({ ...guest, name: e.target.value })}
      />
      <TextInput
        label={t('book.phone')}
        type="tel"
        autoComplete="tel"
        value={guest.phone}
        onChange={(e) => setGuest({ ...guest, phone: e.target.value })}
      />
      <TextInput
        label={t('book.notes')}
        value={guest.notes}
        maxLength={500}
        onChange={(e) => setGuest({ ...guest, notes: e.target.value })}
      />
      <CheckInput label={t('book.consent')} checked={consent} onChange={setConsent} />
      {book.error && <Alert>{errorMessage(book.error, t)}</Alert>}
      <Button disabled={!ready || book.isPending} aria-busy={book.isPending} onClick={submit}>
        {t('book.submit')}
      </Button>
    </Card>
  )
}

type TimesProps = {
  token: string
  tz: string
  day: string
  party: number
  value: string
  onPick: (slot: string) => void
}

function Times({ token, tz, day, party, value, onPick }: TimesProps) {
  const { t, i18n } = useTranslation()
  const slots = useSlots(token, day, party)
  if (slots.isPending) return <p className="text-sm text-muted">{t('book.loading')}</p>
  if (!slots.data?.length) return <p className="text-sm text-muted">{t('book.noTimes')}</p>
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="text-sm font-semibold text-ink-soft">{t('book.time')}</legend>
      <div className="flex flex-wrap gap-2">
        {slots.data.map((s) => (
          <Button
            key={s}
            variant={s === value ? 'primary' : 'ghost'}
            aria-pressed={s === value}
            onClick={() => onPick(s)}
          >
            {new Date(s).toLocaleTimeString(i18n.language, {
              hour: '2-digit',
              minute: '2-digit',
              timeZone: tz,
            })}
          </Button>
        ))}
      </div>
    </fieldset>
  )
}
