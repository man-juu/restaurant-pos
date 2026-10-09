import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import type { AllSettings, PayableRow } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { useSettings } from '../settings/api'
import { useVendors } from './api'
import { useBills, usePayables } from './apApi'
import { BillCard, type BillCan } from './BillCard'
import { BillForm } from './BillForm'

/** FR-PUR-009: what is owed (overdue first), the bills at this outlet and paying them. */
export function BillsTab({
  outletId,
  currency,
  can,
}: {
  outletId: string
  currency: string
  can: BillCan
}) {
  const { t } = useTranslation()
  const bills = useBills(outletId)
  const owed = usePayables()
  const vendors = useVendors()
  const settings = useSettings()
  const [adding, setAdding] = useState(false)
  const methods = activeCodes(settings.data)
  return (
    <div className="flex flex-col gap-3">
      {owed.data && <OwedCard rows={owed.data} currency={currency} />}
      {can.manage && !adding && (
        <Button className="self-start" onClick={() => setAdding(true)}>
          {t('purchasing.bills.new')}
        </Button>
      )}
      {adding && <BillForm outletId={outletId} onDone={() => setAdding(false)} />}
      {bills.error && <Alert>{errorMessage(bills.error, t)}</Alert>}
      {bills.isSuccess && bills.data.length === 0 && (
        <p className="text-ink-soft">{t('purchasing.bills.empty')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {bills.data?.map((b) => (
          <BillCard
            key={b.id}
            bill={b}
            vendor={vendors.data?.find((v) => v.id === b.vendor_id)?.name ?? ''}
            currency={currency}
            can={can}
            methods={methods}
          />
        ))}
      </ul>
    </div>
  )
}

function activeCodes(data?: AllSettings): string[] {
  return (data?.payment_methods.methods ?? []).filter((m) => m.active).map((m) => m.code)
}

function OwedCard({ rows, currency }: { rows: PayableRow[]; currency: string }) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const overdue = rows.filter((r) => r.days_overdue > 0)
  const total = (list: PayableRow[]) =>
    formatMoney(
      list.reduce((s, r) => s + r.balance, 0),
      currency,
      locale,
    )
  return (
    <Card>
      <p className="font-bold">{t('purchasing.bills.owed', { total: total(rows) })}</p>
      <p className={overdue.length ? 'text-sm text-danger' : 'text-sm text-muted'}>
        {t('purchasing.bills.overdue', { count: overdue.length, total: total(overdue) })}
      </p>
    </Card>
  )
}
