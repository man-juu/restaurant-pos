import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import type { CustomerOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useEarn } from './api'
import { GuestPicker } from './GuestPicker'

/** On the paid receipt: give the guest their points (once per receipt, checked on the server). */
export function EarnPoints({ documentId }: { documentId: string }) {
  const { t } = useTranslation()
  const earn = useEarn()
  const [open, setOpen] = useState(false)
  const pick = (c: CustomerOut) => earn.mutate({ document_id: documentId, customer_id: c.id })
  if (earn.data)
    return (
      <p className="text-sm text-good" role="status">
        {t('loyalty.earned', { points: earn.data.points, balance: earn.data.balance })}
      </p>
    )
  return (
    <div className="flex flex-col gap-2">
      {!open && (
        <Button variant="ghost" className="self-start" onClick={() => setOpen(true)}>
          {t('loyalty.give')}
        </Button>
      )}
      {open && <GuestPicker onPick={pick} />}
      {earn.error ? <Alert>{errorMessage(earn.error, t)}</Alert> : null}
    </div>
  )
}
