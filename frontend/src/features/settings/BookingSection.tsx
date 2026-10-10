import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { BookingLinks } from './BookingLinks'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

type Props = { data: AllSettings; canEdit: boolean }
const NUMBERS = [
  'slot_minutes',
  'min_notice_minutes',
  'days_ahead',
  'max_party',
  'max_open_per_phone',
] as const
const num = (v: string) => Number.parseInt(v.replace(/\D/g, ''), 10)
const hhmm = (m: number) =>
  `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
const minutes = (v: string) => {
  const [h, m] = v.split(':').map(Number)
  return h * 60 + (m || 0)
}

/** FR-TBL-010: what guests may book online, the reminder text, and the public links. */
export function BookingSection({ data, canEdit }: Props) {
  const { t } = useTranslation()
  const save = useSaveSetting('booking')
  const cur = data.booking
  const [opens, setOpens] = useState(hhmm(cur?.opens_min ?? 600))
  const [closes, setCloses] = useState(hhmm(cur?.closes_min ?? 1260))
  const [v, setV] = useState(() =>
    Object.fromEntries(NUMBERS.map((f) => [f, String(cur?.[f] ?? '')])),
  )
  const [text, setText] = useState(cur?.reminder_text ?? '')
  const ok = NUMBERS.every((f) => num(v[f]) >= 0) && minutes(closes) > minutes(opens)
  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3">
        <fieldset disabled={!canEdit} className="grid gap-3 sm:grid-cols-2">
          <TextInput
            label={t('settings.booking.opens')}
            type="time"
            value={opens}
            onChange={(e) => setOpens(e.target.value)}
          />
          <TextInput
            label={t('settings.booking.closes')}
            type="time"
            value={closes}
            onChange={(e) => setCloses(e.target.value)}
          />
          {NUMBERS.map((f) => (
            <TextInput
              key={f}
              label={t(`settings.booking.${f}`)}
              inputMode="numeric"
              value={v[f]}
              onChange={(e) => setV({ ...v, [f]: e.target.value })}
            />
          ))}
          <TextInput
            className="sm:col-span-2"
            label={t('settings.booking.reminder_text')}
            maxLength={500}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </fieldset>
        <p className="text-sm text-muted">{t('settings.booking.help')}</p>
        {canEdit && ok && (
          <SaveBar
            mutation={save}
            onSave={() =>
              save.mutate({
                opens_min: minutes(opens),
                closes_min: minutes(closes),
                slot_minutes: num(v.slot_minutes),
                min_notice_minutes: num(v.min_notice_minutes),
                days_ahead: num(v.days_ahead),
                max_party: num(v.max_party),
                max_open_per_phone: num(v.max_open_per_phone),
                reminder_text: text,
              })
            }
          />
        )}
      </Card>
      <BookingLinks />
    </div>
  )
}
