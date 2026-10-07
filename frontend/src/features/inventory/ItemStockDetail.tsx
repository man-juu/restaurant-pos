import { useTranslation } from 'react-i18next'

import { Button, Card } from '../../components/ui'
import type { StockRow } from '../../lib/api/types'
import { formatDate, formatNumber, intlLocale } from '../../lib/format'
import { useBatches, useMovements } from './api'

/** Batches in FEFO order and the latest movements of one item at one outlet. */
export function ItemStockDetail({
  outletId,
  row,
  onClose,
}: {
  outletId: string
  row: StockRow
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const batches = useBatches(outletId, row.item_id)
  const movements = useMovements(outletId, row.item_id)
  const qty = (value: string) => `${formatNumber(Number(value), locale)} ${row.unit_code}`

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" onClick={onClose}>
          {t('catalog.back')}
        </Button>
        <h2 className="font-display text-2xl font-extrabold">{row.name}</h2>
      </div>
      <Card className="flex flex-col gap-2">
        <h3 className="font-bold">{t('inventory.batches')}</h3>
        <p className="text-sm text-ink-soft">{t('inventory.fefo')}</p>
        <ul className="flex flex-col gap-1">
          {batches.data?.map((b) => (
            <li
              key={b.id}
              className="flex flex-wrap justify-between gap-2 border-b border-line py-1.5"
            >
              <span>
                {b.lot_code ?? t('inventory.noLot')}
                <span className="text-ink-soft">
                  {' · '}
                  {b.expiry_date
                    ? t('inventory.expires', { date: formatDate(b.expiry_date, locale) })
                    : t('inventory.noExpiry')}
                </span>
              </span>
              <span className="tabular-nums">{qty(b.qty)}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="flex flex-col gap-2">
        <h3 className="font-bold">{t('inventory.history')}</h3>
        <ul className="flex flex-col gap-1">
          {movements.data?.items.map((m) => (
            <li
              key={m.id}
              className="flex flex-wrap justify-between gap-2 border-b border-line py-1.5"
            >
              <span>
                {t(`inventory.types.${m.movement_type}`)}
                {m.reverses_id && (
                  <span className="text-ink-soft">{` · ${t('inventory.reversal')}`}</span>
                )}
                <span className="block text-xs text-muted">
                  {formatDate(m.business_date, locale)}
                </span>
              </span>
              <span className="tabular-nums">{qty(m.qty)}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  )
}
