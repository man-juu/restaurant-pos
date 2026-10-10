import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useBookingAction, useSuggestions } from './bookingApi'

type Props = { outletId: string; day: string; onDone: () => void }

/** FR-TBL-005, 006: book a party; the server suggests free tables that fit. */
export function ReservationForm({ outletId, day, onDone }: Props) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [party, setParty] = useState('2')
  const [time, setTime] = useState('19:00')
  const [notes, setNotes] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const size = Number.parseInt(party, 10) || 0
  const startsAt = time ? new Date(`${day}T${time}`).toISOString() : ''
  const options = useSuggestions(outletId, startsAt, size)
  const book = useBookingAction()
  const submit = () =>
    book.mutate(
      {
        method: 'POST',
        path: 'reservations',
        body: {
          outlet_id: outletId,
          guest: { name: name.trim(), phone: phone.trim() || null },
          party_size: size,
          starts_at: startsAt,
          table_ids: picked,
          notes: notes.trim() || null,
        },
      },
      { onSuccess: onDone },
    )
  return (
    <Card className="flex flex-col gap-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <TextInput
          label={t('bookings.name')}
          value={name}
          maxLength={120}
          onChange={(e) => setName(e.target.value)}
        />
        <TextInput
          label={t('bookings.phone')}
          type="tel"
          value={phone}
          maxLength={30}
          onChange={(e) => setPhone(e.target.value)}
        />
        <TextInput
          label={t('bookings.party')}
          inputMode="numeric"
          value={party}
          onChange={(e) => setParty(e.target.value)}
        />
        <TextInput
          label={t('bookings.time')}
          type="time"
          value={time}
          onChange={(e) => setTime(e.target.value)}
        />
      </div>
      <TextInput
        label={t('bookings.notes')}
        value={notes}
        maxLength={500}
        onChange={(e) => setNotes(e.target.value)}
      />
      <fieldset className="flex flex-wrap gap-2">
        <legend className="mb-1 text-sm font-semibold text-ink-soft">{t('bookings.tables')}</legend>
        {options.data?.length === 0 && (
          <p className="text-sm text-ink-soft">{t('bookings.noTables')}</p>
        )}
        {options.data?.map((o) => {
          const on = picked.join() === o.table_ids.join()
          return (
            <Button
              key={o.table_ids.join()}
              variant={on ? 'primary' : 'ghost'}
              aria-pressed={on}
              onClick={() => setPicked(o.table_ids)}
            >
              {t('bookings.option', { names: o.names.join(' + '), seats: o.capacity })}
            </Button>
          )
        })}
      </fieldset>
      {book.error && <Alert>{errorMessage(book.error, t)}</Alert>}
      <div className="flex gap-2">
        <Button onClick={submit} disabled={!name.trim() || !picked.length || book.isPending}>
          {t('bookings.save')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('bookings.cancelForm')}
        </Button>
      </div>
    </Card>
  )
}
