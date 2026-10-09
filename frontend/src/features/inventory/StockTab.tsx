import { clsx } from 'clsx'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import type { StockRow } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatMoney, formatNumber, intlLocale } from '../../lib/format'
import { useStock } from './api'
import { ItemStockDetail } from './ItemStockDetail'

export function StockTab({
  outletId,
  showCost,
  currency,
  canAdjust = false,
}: {
  outletId: string
  showCost: boolean
  currency: string
  canAdjust?: boolean
}) {
  const { t, i18n } = useTranslation()
  const stock = useStock(outletId, i18n.language)
  const rows = stock.data?.pages.flatMap((p) => p.items) ?? []
  const [open, setOpen] = useState<StockRow>()

  if (open)
    return (
      <ItemStockDetail
        outletId={outletId}
        row={open}
        canAdjust={canAdjust}
        onClose={() => setOpen(undefined)}
      />
    )
  return (
    <div className="flex flex-col gap-3">
      {stock.error && <Alert>{errorMessage(stock.error, t)}</Alert>}
      {stock.isSuccess && rows.length === 0 && (
        <p className="text-ink-soft">{t('inventory.empty')}</p>
      )}
      <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {rows.map((row) => (
          <li key={row.item_id}>
            <StockLine
              row={row}
              showCost={showCost}
              currency={currency}
              onOpen={() => setOpen(row)}
            />
          </li>
        ))}
      </ul>
      {stock.hasNextPage && (
        <Button variant="ghost" onClick={() => stock.fetchNextPage()}>
          {t('catalog.items.more')}
        </Button>
      )}
    </div>
  )
}

function StockLine({
  row,
  showCost,
  currency,
  onOpen,
}: {
  row: StockRow
  showCost: boolean
  currency: string
  onOpen: () => void
}) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const qty = Number(row.qty)
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex min-h-14 w-full items-center justify-between gap-3 rounded-xl border border-line bg-card px-4 py-2 text-left hover:bg-raised"
    >
      <span className="min-w-0">
        <span className="block truncate font-bold">{row.name}</span>
        <span className="block text-sm text-muted">{row.sku}</span>
        <DaysLeft days={row.days_left} />
      </span>
      <span className="text-right tabular-nums">
        <span className={clsx('block font-bold', qty < 0 && 'text-danger')}>
          {`${formatNumber(qty, locale)} ${row.unit_code}`}
        </span>
        {qty < 0 && <span className="block text-xs text-danger">{t('inventory.negative')}</span>}
        {showCost && row.value !== null && (
          <span className="block text-sm text-ink-soft">
            {formatMoney(row.value, currency, locale)}
          </span>
        )}
      </span>
    </button>
  )
}

/** FR-INV-011: how long the stock lasts at the recent pace (nothing shown without usage). */
function DaysLeft({ days }: { days?: string | null }) {
  const { t } = useTranslation()
  if (days == null) return null
  const n = Number(days)
  return (
    <span className={clsx('block text-xs', n < 2 ? 'text-danger' : 'text-ink-soft')}>
      {t('inventory.daysLeft', { count: Math.floor(n) })}
    </span>
  )
}
