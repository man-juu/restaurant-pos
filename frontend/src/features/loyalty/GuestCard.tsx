import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { CustomerOut, LoyaltyBalance } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useBalance, useRedeem } from './api'

type Money = (v: number) => string

/** FR-SAL-016: a guest's points, their vouchers and turning points into a voucher. */
export function GuestCard({
  guest,
  money,
  canRedeem,
}: {
  guest: CustomerOut
  money: Money
  canRedeem: boolean
}) {
  const { t } = useTranslation()
  const bal = useBalance(guest.id)
  const d = bal.data
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-xl font-bold">{guest.name}</h2>
      {bal.error && <Alert>{errorMessage(bal.error, t)}</Alert>}
      {d && (
        <>
          <p className="text-2xl font-extrabold tabular-nums">
            {t('loyalty.balance', { points: d.balance, value: money(d.balance * d.point_value) })}
          </p>
          {canRedeem && <Redeem guest={guest} data={d} money={money} />}
          <VoucherList data={d} money={money} />
          <ul className="text-sm text-ink-soft">
            {d.entries.map((e) => (
              <li key={e.id}>
                {e.created_at.slice(0, 10)} · {t(`loyalty.kinds.${e.kind}`)} ·{' '}
                {e.points > 0 ? `+${e.points}` : e.points}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  )
}

function VoucherList({ data, money }: { data: LoyaltyBalance; money: Money }) {
  const { t } = useTranslation()
  if (data.vouchers.length === 0) return null
  return (
    <div>
      <h3 className="font-bold">{t('loyalty.vouchers')}</h3>
      <ul className="text-sm">
        {data.vouchers.map((v) => (
          <li key={v.id}>
            <span className="font-mono font-bold">{v.code}</span> · {money(v.amount)}
            {v.expires_on ? ` · ${t('loyalty.until', { date: v.expires_on })}` : ''}
          </li>
        ))}
      </ul>
    </div>
  )
}

function Redeem({
  guest,
  data,
  money,
}: {
  guest: CustomerOut
  data: LoyaltyBalance
  money: Money
}) {
  const { t } = useTranslation()
  const redeem = useRedeem()
  const [points, setPoints] = useState('')
  const [key, setKey] = useState(() => crypto.randomUUID())
  const n = Number.parseInt(points, 10) || 0
  const ok = n >= data.min_redeem_points && n <= data.balance
  const submit = () =>
    redeem.mutate(
      { body: { customer_id: guest.id, points: n }, key },
      { onSuccess: () => (setKey(crypto.randomUUID()), setPoints('')) },
    )
  return (
    <div className="flex flex-col gap-2">
      <TextInput
        label={t('loyalty.points', { min: data.min_redeem_points })}
        inputMode="numeric"
        value={points}
        onChange={(e) => setPoints(e.target.value)}
      />
      {n > 0 && (
        <p className="text-sm">{t('loyalty.worth', { value: money(n * data.point_value) })}</p>
      )}
      {redeem.error ? <Alert>{errorMessage(redeem.error, t)}</Alert> : null}
      {redeem.data && (
        <p className="text-sm text-good" role="status">
          {t('loyalty.made', { code: redeem.data.code })}
        </p>
      )}
      <Button className="self-start" disabled={!ok || redeem.isPending} onClick={submit}>
        {t('loyalty.redeem')}
      </Button>
    </div>
  )
}
