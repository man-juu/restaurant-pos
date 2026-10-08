import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput } from '../../components/form'
import { Alert, Button } from '../../components/ui'
import type { Capabilities } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useOutlets } from '../../lib/session'
import { useTransfers } from './api'
import { RequestForm } from './RequestForm'
import { type Can, TransferCard } from './TransferCard'

function abilities(caps?: Capabilities): Can {
  const has = (code: string) => Boolean(caps?.permissions.includes(code))
  return {
    request: has('transfers.transfer.request'),
    approve: has('transfers.transfer.approve'),
    receive: has('transfers.transfer.receive'),
  }
}

/** FR-TRF-001 to 004: requests in and out of this outlet, and the next step for each. */
export function TransfersPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const outlets = useOutlets()
  const [picked, setPicked] = useState('')
  const outletId = picked || outlets.data?.find((o) => o.is_active)?.id || ''
  const names = Object.fromEntries((outlets.data ?? []).map((o) => [o.id, o.name]))
  const can = abilities(caps)
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('transfers.title')}</h1>
      <SelectInput
        label={t('inventory.outlet')}
        value={outletId}
        onChange={(e) => setPicked(e.target.value)}
        className="max-w-sm"
      >
        {outlets.data?.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </SelectInput>
      {outletId && (
        <>
          <RequestArea outletId={outletId} canRequest={can.request} />
          <TransferList
            outletId={outletId}
            names={names}
            currency={caps?.currency || 'IDR'}
            can={can}
          />
        </>
      )}
    </div>
  )
}

function TransferList({
  outletId,
  names,
  currency,
  can,
}: {
  outletId: string
  names: Record<string, string>
  currency: string
  can: Can
}) {
  const { t, i18n } = useTranslation()
  const list = useTransfers(outletId, i18n.language)
  return (
    <>
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('transfers.empty')}</p>
      )}
      {list.data?.map((tr) => (
        <TransferCard
          key={tr.id}
          transfer={tr}
          outletId={outletId}
          names={names}
          currency={currency}
          can={can}
        />
      ))}
    </>
  )
}

function RequestArea({ outletId, canRequest }: { outletId: string; canRequest: boolean }) {
  const { t } = useTranslation()
  const outlets = useOutlets()
  const [asking, setAsking] = useState(false)
  if (asking)
    return (
      <RequestForm
        outletId={outletId}
        outlets={outlets.data ?? []}
        onDone={() => setAsking(false)}
      />
    )
  if (!canRequest) return null
  return (
    <Button className="self-start" onClick={() => setAsking(true)}>
      {t('transfers.new')}
    </Button>
  )
}
