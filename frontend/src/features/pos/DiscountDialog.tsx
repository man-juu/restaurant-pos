import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { SelectInput, TextInput } from '../../components/form'
import { parseMoney } from '../../lib/money'
import { percentToBp } from '../../lib/percent'
import { useDiscount } from './posApi'
import { ReasonDialog } from './ReasonDialog'

/** FR-SAL-007: a percentage or an amount off a line or the whole order, with a reason. The
 * server checks the role's limit and answers with the limit when it is too much. */
export function DiscountDialog({
  orderId,
  lineId,
  currency,
  onClose,
}: {
  orderId: string
  lineId?: string
  currency: string
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const discount = useDiscount(orderId, i18n.language)
  const [kind, setKind] = useState<'percent' | 'amount'>('percent')
  const [text, setText] = useState('')
  const value = kind === 'percent' ? percentToBp(text) : parseMoney(text, currency)
  return (
    <ReasonDialog
      title={t(lineId ? 'pos.discountLine' : 'pos.discountOrder')}
      confirm={t('pos.applyDiscount')}
      ready={value !== null && value > 0}
      pending={discount.isPending}
      error={discount.error}
      onClose={onClose}
      onConfirm={(reason) =>
        value !== null &&
        discount.mutate({ lineId, body: { kind, value, reason } }, { onSuccess: onClose })
      }
    >
      <SelectInput
        label={t('pos.discountKind')}
        value={kind}
        onChange={(e) => setKind(e.target.value as 'percent' | 'amount')}
      >
        <option value="percent">{t('pos.percent')}</option>
        <option value="amount">{t('pos.amount')}</option>
      </SelectInput>
      <TextInput
        label={t(kind === 'percent' ? 'pos.percentValue' : 'pos.amountValue')}
        inputMode="decimal"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
    </ReasonDialog>
  )
}
