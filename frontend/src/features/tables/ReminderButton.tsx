import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import type { ReservationOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useRemind, whatsappUrl } from '../booking/api'

/** FR-TBL-010: build the reminder from the tenant's text, then staff send it from their own
 * WhatsApp (no messaging service). The text stays on screen to copy for SMS. */
export function ReminderButton({ r }: { r: ReservationOut }) {
  const { t } = useTranslation()
  const remind = useRemind()
  const out = remind.data
  return (
    <div className="flex flex-col gap-2">
      <Button variant="ghost" disabled={remind.isPending} onClick={() => remind.mutate(r.id)}>
        {r.reminded_at ? t('bookings.remindAgain') : t('bookings.remind')}
      </Button>
      {remind.error && <Alert>{errorMessage(remind.error, t)}</Alert>}
      {out && (
        <div className="flex flex-col gap-2 rounded-lg bg-raised p-2 text-sm">
          <p>{out.message}</p>
          {out.phone && (
            <a
              className="font-bold text-accent underline"
              href={whatsappUrl(out.phone, out.message)}
              target="_blank"
              rel="noopener noreferrer"
            >
              {t('bookings.openWhatsApp')}
            </a>
          )}
        </div>
      )}
    </div>
  )
}
