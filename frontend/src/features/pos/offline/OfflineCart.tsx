import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../../components/form'
import { Button, Card } from '../../../components/ui'
import type { OfflinePackOut } from '../../../lib/api/types'
import { formatMoney, intlLocale } from '../../../lib/format'
import { type CartLine, changeQty, checkout, linePrice, orderBody } from './cart'
import type { OfflineState } from './useOffline'

const UNPAID = ''

/** The order being taken offline: lines, the total by the server's rules, one tender. */
export function OfflineCart(props: {
  outletId: string
  channelId: string
  currency: string
  pack: OfflinePackOut
  offline: OfflineState
  lines: CartLine[]
  setLines: (ls: CartLine[]) => void
}) {
  const { t, i18n } = useTranslation()
  const money = (v: number) => formatMoney(v, props.currency, intlLocale(i18n.language))
  const methods = props.pack.methods.filter((m) => m.active)
  const [method, setMethod] = useState(methods[0]?.code ?? UNPAID)
  const [tendered, setTendered] = useState('')
  const c = { ...props, method: method || null, tendered }
  const { totals, plan, ready } = checkout(c)
  const finish = () => {
    props.offline.add({
      body: orderBody({ ...c, payment: plan?.body ?? null }),
      total: plan?.due ?? totals.total,
    })
    props.setLines([])
    setTendered('')
  }
  return (
    <Card className="flex flex-col gap-3">
      <ul className="flex flex-col gap-2">
        {props.lines.map((l) => (
          <li key={l.key} className="flex items-center gap-2">
            <span className="mr-auto">{l.item.name}</span>
            <Button
              variant="ghost"
              aria-label={t('pos.offline.less')}
              onClick={() => props.setLines(changeQty(props.lines, l.key, -1))}
            >
              −
            </Button>
            <span className="tabular-nums">{l.qty}</span>
            <Button
              variant="ghost"
              aria-label={t('pos.offline.more')}
              onClick={() => props.setLines(changeQty(props.lines, l.key, 1))}
            >
              +
            </Button>
            <span className="w-24 text-right tabular-nums">{money(linePrice(l))}</span>
          </li>
        ))}
      </ul>
      <dl className="grid grid-cols-2 gap-1 text-sm">
        <dt>{t('pos.offline.tax')}</dt>
        <dd className="text-right tabular-nums">{money(totals.tax + totals.serviceCharge)}</dd>
        <dt className="font-bold">{t('pos.offline.total')}</dt>
        <dd className="text-right font-bold tabular-nums">{money(plan?.due ?? totals.total)}</dd>
      </dl>
      <SelectInput
        label={t('pos.offline.method')}
        value={method}
        onChange={(e) => setMethod(e.target.value)}
      >
        {methods.map((m) => (
          <option key={m.code} value={m.code}>
            {m.name}
          </option>
        ))}
        <option value={UNPAID}>{t('pos.offline.payLater')}</option>
      </SelectInput>
      {method && (
        <TextInput
          label={t('pos.offline.tendered')}
          inputMode="numeric"
          value={tendered}
          onChange={(e) => setTendered(e.target.value)}
        />
      )}
      {plan && plan.change > 0 && <p>{t('pos.offline.change', { amount: money(plan.change) })}</p>}
      <Button disabled={!ready} onClick={finish}>
        {t('pos.offline.finish')}
      </Button>
    </Card>
  )
}
