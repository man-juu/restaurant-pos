import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'

import { LanguageSwitch } from '../../components/LanguageSwitch'
import { Card } from '../../components/ui'
import type { BookedOut } from '../../lib/api/types'
import { useBookingPage } from './api'
import { BookForm } from './BookForm'

/** FR-TBL-010: the guest's booking page. No sign-in; the link token is the only key. */
export function BookPage() {
  const { t } = useTranslation()
  const { token = '' } = useParams()
  const info = useBookingPage(token)
  const [done, setDone] = useState<BookedOut | null>(null)
  return (
    <main className="min-h-screen bg-ground px-4 py-8 text-ink">
      <div className="mx-auto flex w-full max-w-md flex-col gap-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm text-muted">{info.data?.business}</p>
            <h1 className="font-display text-3xl font-extrabold">
              {info.data ? t('book.title', { outlet: info.data.outlet }) : t('book.titlePlain')}
            </h1>
          </div>
          <LanguageSwitch />
        </div>
        {info.isError && (
          <Card>
            <p role="alert">{t('book.closed')}</p>
          </Card>
        )}
        {info.data && !done && <BookForm token={token} page={info.data} onDone={setDone} />}
        {done && <Booked booked={done} />}
      </div>
    </main>
  )
}

function Booked({ booked }: { booked: BookedOut }) {
  const { t, i18n } = useTranslation()
  const at = new Date(booked.starts_at).toLocaleString(i18n.language, {
    dateStyle: 'full',
    timeStyle: 'short',
  })
  return (
    <Card className="flex flex-col gap-2">
      <h2 className="text-xl font-bold" role="status">
        {t('book.done')}
      </h2>
      <p>{t('book.doneLine', { when: at, party: booked.party_size })}</p>
      <p className="text-sm text-muted">{t('book.pendingHelp')}</p>
    </Card>
  )
}
