import { clsx } from 'clsx'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { PaymentMethod } from '../../lib/api/types'
import { quickCash, type TenderDraft } from './payDraft'

/** One tender: method buttons, amount (when split), cash received with quick notes. */
export function TenderRow({
  row,
  methods,
  single,
  due,
  money,
  onChange,
  onRemove,
}: {
  row: TenderDraft
  methods: PaymentMethod[]
  single: boolean
  due: number
  money: (v: number) => string
  onChange: (row: TenderDraft) => void
  onRemove?: () => void
}) {
  const { t } = useTranslation()
  const cash = methods.find((m) => m.code === row.method)?.kind === 'cash'
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line p-3">
      <div className="flex flex-wrap gap-2" role="group" aria-label={t('pos.method')}>
        {methods.map((m) => (
          <button
            key={m.code}
            type="button"
            aria-pressed={row.method === m.code}
            onClick={() => onChange({ ...row, method: m.code, tendered: '' })}
            className={clsx(
              'min-h-11 rounded-xl border px-3 text-sm font-bold',
              row.method === m.code
                ? 'border-accent bg-raised'
                : 'border-line-strong text-ink-soft',
            )}
          >
            {m.name}
          </button>
        ))}
      </div>
      {!single && (
        <TextInput
          label={t('pos.amount')}
          inputMode="numeric"
          value={row.amount}
          onChange={(e) => onChange({ ...row, amount: e.target.value })}
        />
      )}
      {cash && (
        <>
          <TextInput
            label={t('pos.received')}
            inputMode="numeric"
            value={row.tendered}
            onChange={(e) => onChange({ ...row, tendered: e.target.value })}
          />
          {single && (
            <div className="flex flex-wrap gap-2">
              {quickCash(due).map((v) => (
                <Button
                  key={v}
                  variant="ghost"
                  onClick={() => onChange({ ...row, tendered: String(v) })}
                >
                  {money(v)}
                </Button>
              ))}
            </div>
          )}
        </>
      )}
      {onRemove && (
        <Button variant="ghost" onClick={onRemove}>
          {t('pos.removeTender')}
        </Button>
      )}
    </div>
  )
}
