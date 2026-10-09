import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { ShiftOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { parseMoney } from '../../lib/money'
import { useCashMovement, useCloseShift, useForgetShift, useOpenShift } from './posApi'

/** FR-SAL-009: open the drawer with the float counted in it. */
export function ShiftOpen({ outletId, currency }: { outletId: string; currency: string }) {
  const { t } = useTranslation()
  const open = useOpenShift()
  const [text, setText] = useState('')
  const float = parseMoney(text, currency)
  return (
    <Card className="flex max-w-md flex-col gap-3">
      <h2 className="font-display text-xl font-bold">{t('pos.shift.openTitle')}</h2>
      <p className="text-sm text-ink-soft">{t('pos.shift.openHelp')}</p>
      <TextInput
        label={t('pos.shift.float')}
        inputMode="numeric"
        value={text}
        invalid={text !== '' && float === null}
        onChange={(e) => setText(e.target.value)}
      />
      {open.error ? <Alert>{errorMessage(open.error, t)}</Alert> : null}
      <Button
        disabled={float === null || open.isPending}
        onClick={() => float !== null && open.mutate({ outlet_id: outletId, opening_float: float })}
      >
        {t('pos.shift.open')}
      </Button>
    </Card>
  )
}

/** The open shift: what should be in the drawer, cash in or out, and closing with a count. */
export function ShiftSummary({ shift, currency }: { shift: ShiftOut; currency: string }) {
  const { t, i18n } = useTranslation()
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const [closed, setClosed] = useState<ShiftOut>()
  const forget = useForgetShift()
  const view = closed ?? shift
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-display text-xl font-bold">
        {t(view.status === 'open' ? 'pos.shift.current' : 'pos.shift.closedTitle')}
      </h2>
      <dl className="grid grid-cols-[1fr_auto] gap-x-3 text-sm tabular-nums">
        <dt>{t('pos.shift.float')}</dt>
        <dd className="text-right">{money(view.opening_float)}</dd>
        <dt>{t('pos.shift.cashSales')}</dt>
        <dd className="text-right">{money(view.cash_sales)}</dd>
        <dt>{t('pos.shift.cashIn')}</dt>
        <dd className="text-right">{money(view.cash_in)}</dd>
        <dt>{t('pos.shift.cashOut')}</dt>
        <dd className="text-right">{money(view.cash_out)}</dd>
        <dt className="font-bold">{t('pos.shift.expected')}</dt>
        <dd className="text-right font-bold">{money(view.expected)}</dd>
        {view.variance !== null && view.variance !== undefined && (
          <>
            <dt className="font-bold">{t('pos.shift.variance')}</dt>
            <dd className="text-right font-bold" role="status">
              {money(view.variance)}
            </dd>
          </>
        )}
      </dl>
      {view.status === 'open' && (
        <>
          <CashMovementForm shiftId={view.id} currency={currency} />
          <CloseForm shiftId={view.id} currency={currency} onClosed={setClosed} />
        </>
      )}
      {closed && <Button onClick={() => forget(closed.outlet_id)}>{t('pos.shift.done')}</Button>}
    </Card>
  )
}

function CashMovementForm({ shiftId, currency }: { shiftId: string; currency: string }) {
  const { t } = useTranslation()
  const move = useCashMovement(shiftId)
  const [kind, setKind] = useState<'in' | 'out'>('out')
  const [text, setText] = useState('')
  const [reason, setReason] = useState('')
  const amount = parseMoney(text, currency)
  const ok = amount !== null && amount > 0 && reason.trim() !== ''
  return (
    <div className="grid gap-2 border-t border-line pt-3 sm:grid-cols-3 sm:items-end">
      <SelectInput
        label={t('pos.shift.movement')}
        value={kind}
        onChange={(e) => setKind(e.target.value as 'in' | 'out')}
      >
        <option value="out">{t('pos.shift.kindOut')}</option>
        <option value="in">{t('pos.shift.kindIn')}</option>
      </SelectInput>
      <TextInput
        label={t('pos.amount')}
        inputMode="numeric"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <TextInput
        label={t('pos.shift.reason')}
        value={reason}
        maxLength={200}
        onChange={(e) => setReason(e.target.value)}
      />
      {move.error ? <Alert>{errorMessage(move.error, t)}</Alert> : null}
      <Button
        variant="ghost"
        disabled={!ok || move.isPending}
        onClick={() =>
          ok &&
          move.mutate(
            { kind, amount, reason: reason.trim() },
            { onSuccess: () => (setText(''), setReason('')) },
          )
        }
      >
        {t('pos.shift.record')}
      </Button>
    </div>
  )
}

function CloseForm({
  shiftId,
  currency,
  onClosed,
}: {
  shiftId: string
  currency: string
  onClosed: (s: ShiftOut) => void
}) {
  const { t } = useTranslation()
  const close = useCloseShift(shiftId)
  const [text, setText] = useState('')
  const counted = parseMoney(text, currency)
  return (
    <div className="flex flex-col gap-2 border-t border-line pt-3">
      <p className="text-sm text-ink-soft">{t('pos.shift.closeHelp')}</p>
      <TextInput
        label={t('pos.shift.counted')}
        inputMode="numeric"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      {close.error ? <Alert>{errorMessage(close.error, t)}</Alert> : null}
      <Button
        disabled={counted === null || close.isPending}
        onClick={() => counted !== null && close.mutate({ counted }, { onSuccess: onClosed })}
      >
        {t('pos.shift.close')}
      </Button>
    </div>
  )
}
