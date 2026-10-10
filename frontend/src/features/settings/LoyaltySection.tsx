import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Button, Card } from '../../components/ui'
import type { AllSettings } from '../../lib/api/types'
import { useSaveSetting } from './api'
import { SaveBar } from './shared'

type Props = { data: AllSettings; canEdit: boolean }
const FIELDS = ['earn_per', 'point_value', 'min_redeem_points', 'voucher_valid_days'] as const
const num = (v: string) => Number.parseInt(v.replace(/\D/g, ''), 10)

/** FR-SAL-016: how points are earned and what they are worth; vouchers pay as a method. */
export function LoyaltySection({ data, canEdit }: Props) {
  const { t } = useTranslation()
  const save = useSaveSetting('loyalty')
  const cur = data.loyalty
  const [v, setV] = useState(() =>
    Object.fromEntries(FIELDS.map((f) => [f, String(cur?.[f] ?? '')])),
  )
  const ok = FIELDS.every((f) => num(v[f]) >= (f === 'voucher_valid_days' ? 0 : 1))
  return (
    <Card className="flex flex-col gap-3">
      <fieldset disabled={!canEdit} className="grid gap-3 sm:grid-cols-2">
        {FIELDS.map((f) => (
          <TextInput
            key={f}
            label={t(`settings.loyalty.${f}`)}
            inputMode="numeric"
            value={v[f]}
            onChange={(e) => setV({ ...v, [f]: e.target.value })}
          />
        ))}
      </fieldset>
      <p className="text-sm text-muted">{t('settings.loyalty.help')}</p>
      {canEdit && <VoucherMethod data={data} />}
      {canEdit && ok && (
        <SaveBar
          mutation={save}
          onSave={() =>
            save.mutate({
              earn_per: num(v.earn_per),
              point_value: num(v.point_value),
              min_redeem_points: num(v.min_redeem_points),
              voucher_valid_days: num(v.voucher_valid_days),
            })
          }
        />
      )}
    </Card>
  )
}

/** Vouchers pay through a payment method of kind "voucher"; add one if the business has none. */
function VoucherMethod({ data }: { data: AllSettings }) {
  const { t } = useTranslation()
  const save = useSaveSetting('payment_methods')
  const methods = data.payment_methods.methods ?? []
  if (methods.some((m) => m.kind === 'voucher')) return null
  const add = () =>
    save.mutate({
      methods: [
        ...methods,
        { code: 'voucher', name: t('settings.loyalty.method'), kind: 'voucher', active: true },
      ],
    })
  return (
    <Button variant="ghost" className="self-start" disabled={save.isPending} onClick={add}>
      {t('settings.loyalty.addMethod')}
    </Button>
  )
}
