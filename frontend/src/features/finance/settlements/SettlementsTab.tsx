import { type ReactNode, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput } from '../../../components/form'
import { Alert, Button, Card, StateBadge } from '../../../components/ui'
import type { ReconcileOut, SettlementOut } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { formatDate, formatMoney, intlLocale } from '../../../lib/format'
import { useChannels } from '../../catalog/api'
import { useReconcile, useReverseSettlement, useSettlements } from './settlementApi'
import { SettlementForm } from './SettlementForm'

type Props = { outletId: string; from: string; to: string; currency: string; canManage: boolean }

/** FR-FIN-007: platform payouts against the sales we booked for that platform. */
export function SettlementsTab(props: Props) {
  const { t } = useTranslation()
  const platforms = (useChannels().data ?? []).filter((c) => c.kind === 'platform')
  const [picked, setChannel] = useState('')
  const channelId = picked || platforms[0]?.id || ''
  const [adding, setAdding] = useState(false)
  const rec = useReconcile({ channelId, outletId: props.outletId, from: props.from, to: props.to })
  if (!platforms.length) return <p className="text-ink-soft">{t('settle.noPlatform')}</p>
  return (
    <div className="flex flex-col gap-3">
      <SelectInput
        label={t('settle.platform')}
        value={channelId}
        onChange={(e) => setChannel(e.target.value)}
      >
        {platforms.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </SelectInput>
      {rec.data && <Reconcile rec={rec.data} currency={props.currency} />}
      {props.canManage && !adding && (
        <Button className="self-start" onClick={() => setAdding(true)}>
          {t('settle.new')}
        </Button>
      )}
      {adding && (
        <SettlementForm {...props} channelId={channelId} onDone={() => setAdding(false)} />
      )}
      <List {...props} />
    </div>
  )
}

function Reconcile({ rec, currency }: { rec: ReconcileOut; currency: string }) {
  const { t, i18n } = useTranslation()
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  return (
    <Card>
      <p>{t('settle.booked', { orders: rec.orders, amount: money(rec.booked_gross) })}</p>
      <p>{t('settle.settled', { count: rec.settlements, amount: money(rec.settled_gross) })}</p>
      <p className="text-sm text-muted">
        {t('settle.costs', {
          amount: money(rec.commission + rec.fees),
          pct: rec.commission_pct ?? '-',
        })}
      </p>
      <p className={rec.difference ? 'font-bold text-danger' : 'font-bold'}>
        {t('settle.difference', { amount: money(rec.difference) })}
      </p>
    </Card>
  )
}

function List({ outletId, currency, canManage }: Props) {
  const { t } = useTranslation()
  const rows = useSettlements(outletId)
  const reverse = useReverseSettlement()
  if (rows.error) return <Alert>{errorMessage(rows.error, t)}</Alert>
  return (
    <ul className="flex flex-col gap-2">
      {rows.data?.map((s) => (
        <Row key={s.id} s={s} currency={currency}>
          {canManage && s.status === 'posted' && (
            <Button
              variant="ghost"
              disabled={reverse.isPending}
              onClick={() => reverse.mutate(s.id)}
            >
              {t('settle.reverse')}
            </Button>
          )}
        </Row>
      ))}
      {reverse.error && <Alert>{errorMessage(reverse.error, t)}</Alert>}
    </ul>
  )
}

function Row({
  s,
  currency,
  children,
}: {
  s: SettlementOut
  currency: string
  children: ReactNode
}) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-card p-3">
      <div>
        <p className="font-bold">{`${s.number} · ${formatDate(s.paid_on, locale)}`}</p>
        <p className="text-sm text-muted">
          {t('settle.line', {
            gross: formatMoney(s.gross, currency, locale),
            payout: formatMoney(s.payout, currency, locale),
          })}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <StateBadge state={s.status} label={t(`settle.status.${s.status}`)} />
        {children}
      </div>
    </li>
  )
}
