import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { usePriceList, useEnterDay } from './api'
import { entryOk, listTotal, toEntry } from './salesDraft'

/** FR-SAL-002: what one channel sold today, item by item; saving again replaces it. */
export function EntryGrid({
  outletId,
  on,
  channelId,
  currency,
}: {
  outletId: string
  on: string
  channelId: string
  currency: string
}) {
  const { t, i18n } = useTranslation()
  const list = usePriceList(channelId, on, i18n.language)
  const save = useEnterDay()
  const [qty, setQty] = useState<Record<string, string>>({})
  const [reported, setReported] = useState('')
  const [key, setKey] = useState(() => crypto.randomUUID())
  const locale = intlLocale(i18n.language)
  const subtotal = listTotal(list.data ?? [], qty)
  const submit = () =>
    save.mutate(
      { body: toEntry({ outletId, on, channelId }, qty, reported), key },
      { onSuccess: () => (setQty({}), setReported(''), setKey(crypto.randomUUID())) },
    )
  return (
    <Card className="flex flex-col gap-3">
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('sales.noPrices')}</p>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {list.data?.map((row) => (
          <TextInput
            key={row.item_id}
            label={`${row.name} · ${formatMoney(row.price, currency, locale)}`}
            inputMode="decimal"
            value={qty[row.item_id] ?? ''}
            onChange={(e) => setQty({ ...qty, [row.item_id]: e.target.value })}
          />
        ))}
      </div>
      <p className="font-semibold">
        {t('sales.listTotal', { total: formatMoney(subtotal, currency, locale) })}
      </p>
      <TextInput
        label={t('sales.reported')}
        inputMode="numeric"
        className="max-w-xs"
        value={reported}
        onChange={(e) => setReported(e.target.value)}
      />
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      <Button
        className="self-start"
        disabled={!entryOk(qty, reported) || save.isPending}
        onClick={submit}
      >
        {t('sales.save')}
      </Button>
    </Card>
  )
}
