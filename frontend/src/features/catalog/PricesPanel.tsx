import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { ChannelOut, PriceOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useOutlets } from '../../lib/session'
import { formatDate, formatMoney, intlLocale } from '../../lib/format'
import { parseMoney } from '../../lib/money'
import { SaveBar } from '../settings/shared'
import { useChannels, useDeletePrice, usePrices, useSetPrice } from './api'
import { todayIso } from './labels'

interface Props {
  itemId: string
  canEdit: boolean
  currency: string
}

/** FR-CAT-004: list price per channel from a start date; promotions are discounts on sales. */
export function PricesPanel({ itemId, canEdit, currency }: Props) {
  const { t } = useTranslation()
  const channels = useChannels()
  const prices = usePrices(itemId)
  const list = channels.data ?? []

  return (
    <Card className="flex flex-col gap-4">
      <h2 className="font-display text-xl font-extrabold">{t('catalog.prices.title')}</h2>
      <p className="text-sm text-ink-soft">{t('catalog.prices.help')}</p>
      {channels.isSuccess && list.length === 0 && (
        <p className="text-ink-soft">{t('catalog.prices.noChannels')}</p>
      )}
      {prices.error && <Alert>{errorMessage(prices.error, t)}</Alert>}
      {prices.data?.length === 0 && <p className="text-ink-soft">{t('catalog.prices.empty')}</p>}
      <PriceList
        rows={prices.data ?? []}
        channels={list}
        itemId={itemId}
        canEdit={canEdit}
        currency={currency}
      />
      {canEdit && list.length > 0 && (
        <PriceForm itemId={itemId} channels={list} currency={currency} />
      )}
    </Card>
  )
}

function PriceList({
  rows,
  channels,
  itemId,
  canEdit,
  currency,
}: Props & { rows: PriceOut[]; channels: ChannelOut[] }) {
  const { t, i18n } = useTranslation()
  const remove = useDeletePrice(itemId)
  const locale = intlLocale(i18n.language)
  const today = todayIso()
  const name = (id: string) => channels.find((c) => c.id === id)?.name ?? '—'

  return (
    <>
      <ul className="flex flex-col gap-2">
        {rows.map((p) => (
          <li
            key={p.id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line px-3 py-2"
          >
            <span>
              <b>{name(p.channel_id)}</b> {p.outlet_id && <OutletName id={p.outlet_id} />}
              <span className="text-ink-soft">
                {t('catalog.prices.from', { date: formatDate(p.valid_from, locale) })}
              </span>
            </span>
            <span className="flex items-center gap-2">
              <span className="font-bold tabular-nums">
                {formatMoney(p.price, currency, locale)}
              </span>
              {/* Started prices are history for margin reports; only planned ones can go. */}
              {canEdit && p.valid_from > today && (
                <Button
                  variant="ghost"
                  onClick={() => remove.mutate(p.id)}
                  disabled={remove.isPending}
                >
                  {t('settings.remove')}
                </Button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {remove.error ? <Alert>{errorMessage(remove.error, t)}</Alert> : null}
    </>
  )
}

function PriceForm({
  itemId,
  channels,
  currency,
}: {
  itemId: string
  channels: ChannelOut[]
  currency: string
}) {
  const { t } = useTranslation()
  const setPrice = useSetPrice(itemId)
  const [channelId, setChannelId] = useState(channels[0].id)
  const [from, setFrom] = useState(todayIso)
  const [amount, setAmount] = useState('')
  const [outletId, setOutletId] = useState('')
  const outlets = (useOutlets().data ?? []).filter((o) => o.is_active)
  const minor = parseMoney(amount, currency)

  return (
    <div className="grid items-end gap-3 sm:grid-cols-3">
      <SelectInput
        label={t('catalog.prices.channel')}
        value={channelId}
        onChange={(e) => setChannelId(e.target.value)}
      >
        {channels.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </SelectInput>
      <SelectInput
        label={t('catalog.prices.outlet')}
        value={outletId}
        onChange={(e) => setOutletId(e.target.value)}
      >
        <option value="">{t('catalog.prices.allOutlets')}</option>
        {outlets.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </SelectInput>
      <TextInput
        label={t('catalog.prices.startDate')}
        type="date"
        value={from}
        onChange={(e) => setFrom(e.target.value)}
      />
      <TextInput
        label={t('catalog.prices.amount', { currency })}
        inputMode="decimal"
        value={amount}
        invalid={amount !== '' && minor === null}
        onChange={(e) => setAmount(e.target.value)}
      />
      <div className="sm:col-span-3">
        <SaveBar
          mutation={setPrice}
          disabled={minor === null || !from}
          onSave={() =>
            minor !== null &&
            setPrice.mutate({
              channel_id: channelId,
              valid_from: from,
              price: minor,
              outlet_id: outletId || null,
            })
          }
        />
      </div>
    </div>
  )
}

/** FR-TEN-011: a price that applies to one outlet only. */
function OutletName({ id }: { id: string }) {
  const { t } = useTranslation()
  const name = useOutlets().data?.find((o) => o.id === id)?.name ?? '…'
  return (
    <span className="text-sm text-accent">{t('catalog.prices.onlyAt', { outlet: name })} </span>
  )
}
