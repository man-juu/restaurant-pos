import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput } from '../../components/form'
import type { PaymentMethod } from '../../lib/api/types'
import { useRefund } from './posApi'
import { ReasonDialog } from './ReasonDialog'

/** FR-SAL-008: ask for a refund of a paid order; a manager approves it unless the owner asks. */
export function RefundDialog({
  orderId,
  methods,
  defaultMethod,
  onClose,
}: {
  orderId: string
  methods: PaymentMethod[]
  defaultMethod: string
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const refund = useRefund(orderId, i18n.language)
  const [key] = useState(() => crypto.randomUUID())
  const [method, setMethod] = useState(defaultMethod)
  const [effect, setEffect] = useState<'return' | 'waste'>('return')
  return (
    <ReasonDialog
      title={t('pos.refundTitle')}
      confirm={t('pos.refundAsk')}
      pending={refund.isPending}
      error={refund.error}
      onClose={onClose}
      onConfirm={(reason) =>
        refund.mutate(
          { body: { reason, method, stock_effect: effect }, key },
          { onSuccess: onClose },
        )
      }
    >
      <SelectInput
        label={t('pos.refundMethod')}
        value={method}
        onChange={(e) => setMethod(e.target.value)}
      >
        {methods.map((m) => (
          <option key={m.code} value={m.code}>
            {m.name}
          </option>
        ))}
      </SelectInput>
      <SelectInput
        label={t('pos.stockEffect')}
        value={effect}
        onChange={(e) => setEffect(e.target.value as 'return' | 'waste')}
      >
        <option value="return">{t('pos.stockReturn')}</option>
        <option value="waste">{t('pos.stockWaste')}</option>
      </SelectInput>
    </ReasonDialog>
  )
}
