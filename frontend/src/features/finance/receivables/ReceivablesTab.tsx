import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../../components/ui'
import type { AllSettings } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { useSettings } from '../../settings/api'
import { useApAging, useArAging, useInvoices } from './arApi'
import { AgingTable } from './AgingTable'
import { InvoiceCard } from './InvoiceCard'
import { InvoiceForm } from './InvoiceForm'

export type ArCan = { view: boolean; manage: boolean; payables: boolean }

/** FR-SAL-011, FR-FIN-006: wholesale invoices, money owed to us and by us, by age. */
export function ReceivablesTab({
  outletId,
  currency,
  can,
}: {
  outletId: string
  currency: string
  can: ArCan
}) {
  const { t } = useTranslation()
  const invoices = useInvoices(can.view ? outletId : '')
  const methods = activeMethods(useSettings().data)
  const [adding, setAdding] = useState(false)
  return (
    <div className="flex flex-col gap-3">
      <Aging can={can} currency={currency} />
      {can.manage && !adding && (
        <Button className="self-start" onClick={() => setAdding(true)}>
          {t('ar.new')}
        </Button>
      )}
      {adding && <InvoiceForm outletId={outletId} onDone={() => setAdding(false)} />}
      {invoices.error && <Alert>{errorMessage(invoices.error, t)}</Alert>}
      {invoices.isSuccess && invoices.data.length === 0 && (
        <p className="text-ink-soft">{t('ar.empty')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {invoices.data?.map((inv) => (
          <InvoiceCard
            key={inv.id}
            inv={inv}
            currency={currency}
            canManage={can.manage}
            methods={methods}
          />
        ))}
      </ul>
    </div>
  )
}

function Aging({ can, currency }: { can: ArCan; currency: string }) {
  const { t } = useTranslation()
  const ar = useArAging(can.view)
  const ap = useApAging(can.payables)
  return (
    <>
      {ar.data && (
        <AgingTable title={t('ar.aging.receivable')} rows={ar.data} currency={currency} />
      )}
      {ap.data && <AgingTable title={t('ar.aging.payable')} rows={ap.data} currency={currency} />}
    </>
  )
}

const activeMethods = (data?: AllSettings) =>
  (data?.payment_methods.methods ?? []).filter((m) => m.active).map((m) => m.code)
