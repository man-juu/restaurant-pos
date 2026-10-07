import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { StockDocument } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatNumber, intlLocale } from '../../lib/format'
import { useDecide, useDocument, useSaveCounted, useSubmitCount } from './docApi'

const QTY = /^\d{1,14}([.,]\d{1,4})?$/

/** Enter counted quantities (base units), save, submit; approvers decide submitted counts. */
export function CountSheet({
  countId,
  canApprove,
  onClose,
}: {
  countId: string
  canApprove: boolean
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const count = useDocument('counts', countId, i18n.language)
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" onClick={onClose}>
          {t('catalog.back')}
        </Button>
        <h2 className="font-display text-2xl font-extrabold">{count.data?.number}</h2>
      </div>
      {count.error && <Alert>{errorMessage(count.error, t)}</Alert>}
      {count.data && <Sheet key={count.data.status} doc={count.data} canApprove={canApprove} />}
    </div>
  )
}

function Sheet({ doc, canApprove }: { doc: StockDocument; canApprove: boolean }) {
  const { t } = useTranslation()
  const save = useSaveCounted()
  const submit = useSubmitCount()
  const decide = useDecide('counts')
  const lines = doc.lines ?? []
  const editable = doc.status === 'draft'
  const [counted, setCounted] = useState<Record<string, string>>(() =>
    Object.fromEntries(lines.map((ln) => [ln.item_id, ln.counted_qty ?? ''])),
  )
  const filled = Object.entries(counted).filter(([, v]) => QTY.test(v))
  const body = {
    lines: filled.map(([item_id, v]) => ({ item_id, counted_qty: v.replace(',', '.') })),
  }
  const error = save.error ?? submit.error ?? decide.error

  return (
    <Card className="flex flex-col gap-3">
      {doc.blind && editable && (
        <p className="text-sm text-ink-soft">{t('inventory.docs.blindHelp')}</p>
      )}
      <CountLines doc={doc} counted={counted} onChange={setCounted} />
      {editable && (
        <div className="flex flex-wrap gap-3">
          <Button
            variant="ghost"
            onClick={() => save.mutate({ id: doc.id, body })}
            disabled={filled.length === 0}
          >
            {t('settings.save')}
          </Button>
          <Button
            onClick={() =>
              save.mutate({ id: doc.id, body }, { onSuccess: () => submit.mutate(doc.id) })
            }
            disabled={filled.length !== lines.length}
          >
            {t('inventory.docs.submit')}
          </Button>
        </div>
      )}
      {canApprove && doc.status === 'submitted' && (
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => decide.mutate({ id: doc.id, approve: true })}>
            {t('inventory.docs.approve')}
          </Button>
          <Button variant="ghost" onClick={() => decide.mutate({ id: doc.id, approve: false })}>
            {t('inventory.docs.reject')}
          </Button>
        </div>
      )}
      {error ? <Alert>{errorMessage(error, t)}</Alert> : null}
    </Card>
  )
}

function CountLines({
  doc,
  counted,
  onChange,
}: {
  doc: StockDocument
  counted: Record<string, string>
  onChange: (counted: Record<string, string>) => void
}) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const system = (qty: string | null | undefined, unit: string) =>
    qty === null || qty === undefined
      ? ''
      : t('inventory.docs.system', { qty: `${formatNumber(Number(qty), locale)} ${unit}` })
  return (
    <ul className="flex flex-col gap-2">
      {(doc.lines ?? []).map((ln) => (
        <li
          key={ln.item_id}
          className="grid items-end gap-3 border-b border-line pb-2 sm:grid-cols-[2fr_1fr_1fr]"
        >
          <span className="self-center font-semibold">{ln.name}</span>
          <span className="self-center text-sm text-ink-soft">
            {system(ln.system_qty, ln.unit_code)}
          </span>
          <TextInput
            label={t('inventory.docs.counted', { unit: ln.unit_code })}
            inputMode="decimal"
            disabled={doc.status !== 'draft'}
            value={counted[ln.item_id] ?? ''}
            onChange={(e) => onChange({ ...counted, [ln.item_id]: e.target.value })}
          />
        </li>
      ))}
    </ul>
  )
}
