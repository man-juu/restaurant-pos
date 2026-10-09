import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { useOpenOrders } from './posApi'

/** Orders still open at this outlet (from any till or waiter), and starting a new one. */
export function OpenOrders({
  outletId,
  currency,
  onOpen,
  onNew,
  creating,
}: {
  outletId: string
  currency: string
  onOpen: (id: string) => void
  onNew: (label: string) => void
  creating: boolean
}) {
  const { t, i18n } = useTranslation()
  const orders = useOpenOrders(outletId)
  const [label, setLabel] = useState('')
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-xl font-bold">{t('pos.openOrders')}</h2>
      <div className="flex flex-wrap items-end gap-2">
        <TextInput
          label={t('pos.label')}
          value={label}
          maxLength={60}
          onChange={(e) => setLabel(e.target.value)}
        />
        <Button disabled={creating} onClick={() => (onNew(label.trim()), setLabel(''))}>
          {t('pos.newOrder')}
        </Button>
      </div>
      {orders.error && <Alert>{errorMessage(orders.error, t)}</Alert>}
      {orders.isSuccess && orders.data.length === 0 && (
        <p className="text-ink-soft">{t('pos.noOpenOrders')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {orders.data?.map((o) => (
          <li key={o.id}>
            <button
              type="button"
              onClick={() => onOpen(o.id)}
              className="flex min-h-12 w-full items-center justify-between gap-2 rounded-xl border border-line px-3 text-left hover:bg-raised"
            >
              <span>
                <b>{o.label ?? o.number}</b>{' '}
                <span className="text-sm text-ink-soft">
                  {t('pos.lineCount', { count: o.lines })}
                </span>
              </span>
              <span className="tabular-nums">
                {formatMoney(o.total, currency, intlLocale(i18n.language))}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  )
}
