import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useOutlets } from '../../lib/session'
import type { BookingLinkOut } from '../../lib/api/types'
import { bookingUrl, useBookingLinks, useLinkAction } from '../booking/api'

/** Public booking links per outlet. The full address is shown once, right after it is made
 * (only a hash is stored); switching a link off is final, so a leaked link can be retired. */
function useChosenOutlet() {
  const outlets = (useOutlets().data ?? []).filter((o) => o.is_active)
  const [outletId, setOutletId] = useState('')
  return { outlets, chosen: outletId || outlets[0]?.id || '', setOutletId }
}

export function BookingLinks() {
  const { t } = useTranslation()
  const { outlets, chosen, setOutletId } = useChosenOutlet()
  const links = useBookingLinks(chosen)
  const { create, disable } = useLinkAction()
  const error = create.error ?? disable.error ?? links.error
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="text-lg font-bold">{t('settings.booking.links')}</h2>
      <SelectInput
        label={t('settings.booking.outlet')}
        value={chosen}
        onChange={(e) => setOutletId(e.target.value)}
      >
        {outlets.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </SelectInput>
      <Button
        className="self-start"
        disabled={!chosen || create.isPending}
        onClick={() => create.mutate(chosen)}
      >
        {t('settings.booking.newLink')}
      </Button>
      {create.data && <FreshLink token={create.data.token} />}
      {error && <Alert>{errorMessage(error, t)}</Alert>}
      <LinkRows links={links.data ?? []} disable={disable} />
    </Card>
  )
}

type RowsProps = {
  links: BookingLinkOut[]
  disable: { isPending: boolean; mutate: (id: string) => void }
}

function LinkRows({ links, disable }: RowsProps) {
  const { t, i18n } = useTranslation()
  const [asking, setAsking] = useState('') // two taps to switch a link off for good
  return (
    <ul className="flex flex-col gap-2">
      {links.map((l) => (
        <li key={l.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span>
            {t('settings.booking.linkLine', {
              hint: l.hint,
              date: new Date(l.created_at).toLocaleDateString(i18n.language),
            })}
          </span>
          {l.disabled_at ? (
            <span className="text-muted">{t('settings.booking.off')}</span>
          ) : (
            <Button
              variant="ghost"
              disabled={disable.isPending}
              onClick={() => (asking === l.id ? disable.mutate(l.id) : setAsking(l.id))}
            >
              {asking === l.id ? t('settings.booking.offConfirm') : t('settings.booking.disable')}
            </Button>
          )}
        </li>
      ))}
    </ul>
  )
}

function FreshLink({ token }: { token: string }) {
  const { t } = useTranslation()
  const url = bookingUrl(token)
  return (
    <div className="flex flex-col gap-1 rounded-lg bg-raised p-2 text-sm" role="status">
      <p>{t('settings.booking.copyOnce')}</p>
      <code className="break-all">{url}</code>
      <Button
        variant="ghost"
        className="self-start"
        onClick={() => navigator.clipboard?.writeText(url)}
      >
        {t('settings.booking.copy')}
      </Button>
    </div>
  )
}
