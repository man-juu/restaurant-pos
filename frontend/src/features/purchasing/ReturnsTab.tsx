import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, StateBadge } from '../../components/ui'
import type { VendorReturnOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatDate, formatMoney, intlLocale } from '../../lib/format'
import { useVendors } from './api'
import { useApAction, useReturns } from './apApi'
import { ReturnForm } from './ReturnForm'

type Can = { create: boolean; reverse: boolean; credit: boolean }

/** FR-PUR-008: returns to vendors at this outlet and the credit notes they bring. */
export function ReturnsTab({
  outletId,
  currency,
  can,
}: {
  outletId: string
  currency: string
  can: Can
}) {
  const { t } = useTranslation()
  const list = useReturns(outletId)
  const [adding, setAdding] = useState(false)
  return (
    <div className="flex flex-col gap-3">
      {can.create && !adding && (
        <Button className="self-start" onClick={() => setAdding(true)}>
          {t('purchasing.returns.new')}
        </Button>
      )}
      {adding && <ReturnForm outletId={outletId} onDone={() => setAdding(false)} />}
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('purchasing.returns.empty')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {list.data?.map((r) => (
          <ReturnRow key={r.id} row={r} currency={currency} can={can} />
        ))}
      </ul>
    </div>
  )
}

function ReturnRow({ row, currency, can }: { row: VendorReturnOut; currency: string; can: Can }) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const vendors = useVendors()
  const vendor = vendors.data?.find((v) => v.id === row.vendor_id)?.name ?? ''
  const open = row.status === 'posted' && !row.credit_note_number
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-line bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-bold">{`${row.number} · ${vendor}`}</p>
          <p className="text-sm text-muted">
            {t('purchasing.returns.line', {
              date: formatDate(row.business_date, locale),
              reason: t(`purchasing.returns.reasons.${row.reason}`),
              credit: formatMoney(row.credit_amount, currency, locale),
            })}
          </p>
          {row.credit_note_number && (
            <p className="text-sm">
              {t('purchasing.returns.credited', { no: row.credit_note_number })}
            </p>
          )}
        </div>
        <StateBadge state={row.status} label={t(`purchasing.returns.status.${row.status}`)} />
      </div>
      {open && <ReturnActions id={row.id} can={can} />}
    </li>
  )
}

function ReturnActions({ id, can }: { id: string; can: Can }) {
  const { t } = useTranslation()
  const action = useApAction()
  const [note, setNote] = useState('')
  const credit = () =>
    action.mutate({
      path: `returns/${id}/credit-note`,
      body: { credit_note_number: note.trim(), credited_on: new Date().toISOString().slice(0, 10) },
    })
  return (
    <div className="flex flex-wrap items-end gap-2">
      {can.credit && (
        <>
          <TextInput
            label={t('purchasing.returns.creditNote')}
            value={note}
            maxLength={80}
            onChange={(e) => setNote(e.target.value)}
          />
          <Button variant="ghost" disabled={!note.trim() || action.isPending} onClick={credit}>
            {t('purchasing.returns.recordCredit')}
          </Button>
        </>
      )}
      {can.reverse && (
        <Button
          variant="ghost"
          disabled={action.isPending}
          onClick={() => action.mutate({ path: `returns/${id}/reverse` })}
        >
          {t('purchasing.returns.reverse')}
        </Button>
      )}
      {action.error ? <Alert>{errorMessage(action.error, t)}</Alert> : null}
    </div>
  )
}
