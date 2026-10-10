import { useTranslation } from 'react-i18next'

import { Button, Card } from '../../components/ui'
import type { StockRow } from '../../lib/api/types'
import { formatDate, formatNumber, intlLocale } from '../../lib/format'
import { useBatches, useMovements } from './api'
import { labelsUrl } from './locations/locationApi'
import { SetOnHand } from './SetOnHand'

/** Batches in FEFO order and the latest movements of one item at one outlet. */
export function ItemStockDetail({
  outletId,
  row,
  canAdjust = false,
  onClose,
}: {
  outletId: string
  row: StockRow
  canAdjust?: boolean
  onClose: () => void
}) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
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
      {canAdjust && row.tracking_mode === 'estimated' && (
        <SetOnHand outletId={outletId} row={row} />
      )}
      <BatchList outletId={outletId} row={row} />
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

/** Batches in FEFO order, with a printable QR label for each (FR-INV-019). */
function BatchList({ outletId, row }: { outletId: string; row: StockRow }) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const batches = useBatches(outletId, row.item_id)
  const ids = (batches.data ?? []).map((b) => b.id)
  const link = 'text-sm font-semibold text-accent underline'
  return (
    <Card className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-bold">{t('inventory.batches')}</h3>
        <span className="flex gap-3">
          <a className={link} href={labelsUrl(outletId, i18n.language, { item: [row.item_id] })}>
            {t('labels.item')}
          </a>
          {ids.length > 0 && (
            <a className={link} href={labelsUrl(outletId, i18n.language, { batch: ids })}>
              {t('labels.batches')}
            </a>
          )}
        </span>
      </div>
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
            <span className="flex items-center gap-3">
              <span className="tabular-nums">{`${formatNumber(Number(b.qty), locale)} ${row.unit_code}`}</span>
              <a className={link} href={labelsUrl(outletId, i18n.language, { batch: [b.id] })}>
                {t('labels.one')}
              </a>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
