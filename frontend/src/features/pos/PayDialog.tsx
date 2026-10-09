import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button } from '../../components/ui'
import type { PaymentMethod, PosOrderOut, PosSettings } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, intlLocale } from '../../lib/format'
import { parseMoney } from '../../lib/money'
import { payPlan, type TenderDraft } from './payDraft'
import { usePay } from './posApi'
import { TenderRow } from './TenderRow'

/** FR-SAL-006: one or more tenders, change from cash, optional tip; the server checks it all. */
export function PayDialog({
  order,
  methods,
  pos,
  currency,
  onDone,
  onClose,
}: {
  order: PosOrderOut
  methods: PaymentMethod[]
  pos: PosSettings
  currency: string
  onDone: () => void
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const pay = usePay(order.id, i18n.language)
  const [key] = useState(() => crypto.randomUUID())
  const { rows, setRows, tipText, setTip, plan, blank } = usePayState(order, methods, pos, currency)
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const setRow = (i: number, row: TenderDraft) => setRows(rows.map((r, j) => (j === i ? row : r)))
  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 flex max-h-[92vh] w-[min(94vw,520px)] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-2xl border border-line-strong bg-card p-5 text-ink shadow-2xl">
          <Dialog.Title className="font-display text-2xl font-bold">
            {t('pos.due', { amount: money(plan.due) })}
          </Dialog.Title>
          <Dialog.Description className="text-sm text-ink-soft">
            {plan.rounding !== 0
              ? t('pos.rounding', { amount: money(plan.rounding) })
              : t('pos.payHelp')}
          </Dialog.Description>
          {pos.tips_enabled && (
            <TextInput
              label={t('pos.tip')}
              inputMode="numeric"
              value={tipText}
              onChange={(e) => setTip(e.target.value)}
            />
          )}
          {rows.map((row, i) => (
            <TenderRow
              key={i}
              row={row}
              methods={methods}
              single={rows.length === 1}
              due={plan.due}
              money={money}
              onChange={(r) => setRow(i, r)}
              onRemove={rows.length > 1 ? () => setRows(rows.filter((_, j) => j !== i)) : undefined}
            />
          ))}
          <Button variant="ghost" onClick={() => setRows([...rows, blank()])}>
            {t('pos.splitPayment')}
          </Button>
          <p className="text-lg font-bold tabular-nums" role="status">
            {plan.change > 0
              ? t('pos.change', { amount: money(plan.change) })
              : t('pos.paid', { amount: money(plan.paid) })}
          </p>
          {pay.error ? <Alert>{errorMessage(pay.error, t)}</Alert> : null}
          <div className="flex flex-wrap gap-2">
            <Button
              disabled={!plan.body || pay.isPending}
              aria-busy={pay.isPending}
              onClick={() =>
                plan.body && pay.mutate({ body: plan.body, key }, { onSuccess: onDone })
              }
            >
              {t('pos.confirmPay')}
            </Button>
            <Button variant="ghost" onClick={onClose}>
              {t('catalog.cancel')}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/** Tenders and tip being typed, and the plan the server would accept. */
function usePayState(
  order: PosOrderOut,
  methods: PaymentMethod[],
  pos: PosSettings,
  currency: string,
) {
  const blank = (): TenderDraft => ({
    method: methods[0]?.code ?? 'cash',
    amount: '',
    tendered: '',
  })
  const [rows, setRows] = useState<TenderDraft[]>(() => [blank()])
  const [tipText, setTip] = useState('')
  const tip = pos.tips_enabled ? (parseMoney(tipText || '0', currency) ?? 0) : 0
  const plan = payPlan({
    total: order.totals.total,
    tip,
    rows,
    methods,
    roundingStep: pos.cash_rounding_step ?? 0,
    currency,
  })
  return { rows, setRows, tipText, setTip, plan, blank }
}
