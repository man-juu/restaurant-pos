import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, SelectInput } from '../../components/form'
import { Button } from '../../components/ui'
import type { TableSessionOut } from '../../lib/api/types'
import { useOrder } from '../pos/posApi'
import { useSessionStep } from './tablesApi'

/** FR-TBL-003 split by item: tick the lines that go on a new bill. Equal shares or amounts
 * are paid as several tenders in the pay dialog. */
export function SplitBill({ session, onDone }: { session: TableSessionOut; onDone: () => void }) {
  const { t, i18n } = useTranslation()
  const open = session.orders.filter((o) => o.status === 'open' && o.lines > 0)
  const [orderId, setOrderId] = useState(open[0]?.id ?? '')
  const order = useOrder(orderId || undefined, i18n.language)
  const step = useSessionStep(session.id)
  const [picked, setPicked] = useState<string[]>([])
  const lines = (order.data?.lines ?? []).filter((l) => l.status !== 'void')
  return (
    <div className="flex flex-col gap-2 rounded-xl border border-line p-3">
      <SelectInput
        label={t('tables.fromBill')}
        value={orderId}
        onChange={(e) => (setOrderId(e.target.value), setPicked([]))}
      >
        {open.map((o) => (
          <option key={o.id} value={o.id}>
            {o.number}
          </option>
        ))}
      </SelectInput>
      {lines.map((l) => (
        <CheckInput
          key={l.id}
          label={`${Number(l.qty)} × ${l.name}`}
          checked={picked.includes(l.id)}
          onChange={(on) => setPicked(on ? [...picked, l.id] : picked.filter((p) => p !== l.id))}
        />
      ))}
      <Button
        disabled={picked.length === 0 || picked.length === lines.length || step.isPending}
        onClick={() =>
          step.mutate(
            { kind: 'split', from_order_id: orderId, line_ids: picked },
            { onSuccess: onDone },
          )
        }
      >
        {t('tables.splitConfirm')}
      </Button>
    </div>
  )
}
