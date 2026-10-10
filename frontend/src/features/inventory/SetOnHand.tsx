import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { StockRow } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { useUnits } from '../catalog/api'
import { todayIso } from '../catalog/labels'
import { useSetOnHand } from './docApi'

const QTY = /^\d{1,12}([.,]\d{1,4})?$/

/** Estimated items (rice, oil): one step to replace the guess with what is really there. */
export function SetOnHand({ outletId, row }: { outletId: string; row: StockRow }) {
  const { t } = useTranslation()
  const units = useUnits()
  const save = useSetOnHand()
  const [qty, setQty] = useState('')
  const unit = units.data?.find((u) => u.code === row.unit_code)
  const valid = QTY.test(qty) && Boolean(unit)

  return (
    <Card className="flex flex-col gap-3">
      <h3 className="font-bold">{t('inventory.setOnHand.title')}</h3>
      <p className="text-sm text-muted">{t('inventory.setOnHand.help')}</p>
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      {save.isSuccess && <p className="text-sm text-good">{t('inventory.setOnHand.done')}</p>}
      <div className="flex flex-wrap items-end gap-3">
        <TextInput
          label={t('inventory.setOnHand.qty', { unit: row.unit_code })}
          inputMode="decimal"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
        />
        <Button
          disabled={!valid || save.isPending}
          aria-busy={save.isPending}
          onClick={() =>
            unit &&
            save.mutate({
              outlet_id: outletId,
              item_id: row.item_id,
              qty: qty.replace(',', '.'),
              unit_id: unit.id,
              business_date: todayIso(),
            })
          }
        >
          {t('inventory.setOnHand.save')}
        </Button>
      </div>
    </Card>
  )
}
