import { useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Button } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { SaleReceiptOut } from '../../lib/api/types'
import { formatMoney, intlLocale } from '../../lib/format'
import { receiptBytes } from '../../lib/print/layouts'
import { usePrinter } from '../../lib/print/usePrinter'

/** FR-SAL-010: print on the Bluetooth printer, or open the PDF (download, share, email). */
export function PrintButtons({ orderId, currency }: { orderId: string; currency: string }) {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const printer = usePrinter()
  const lang = i18n.language.slice(0, 2)
  const money = (v: number) => formatMoney(v, currency, intlLocale(i18n.language))
  const printReceipt = async () => {
    const r = await client.fetchQuery({
      queryKey: ['receipt', orderId, lang],
      queryFn: () =>
        request<SaleReceiptOut>('GET', `/api/v1/pos/orders/${orderId}/receipt?lang=${lang}`),
      staleTime: 0,
    })
    await printer.print(receiptBytes(r, t, money))
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      {printer.supported && !printer.name && (
        <Button variant="ghost" disabled={printer.busy} onClick={() => void printer.connect()}>
          {t('receipt.connect')}
        </Button>
      )}
      {printer.name && (
        <Button variant="ghost" disabled={printer.busy} onClick={() => void printReceipt()}>
          {t('receipt.print', { printer: printer.name })}
        </Button>
      )}
      <a
        className="text-sm font-semibold text-accent underline"
        href={`/api/v1/pos/orders/${orderId}/receipt/pdf?lang=${lang}`}
        target="_blank"
        rel="noreferrer"
      >
        {t('receipt.pdf')}
      </a>
      {!printer.supported && (
        <span className="text-sm text-ink-soft">{t('receipt.noBluetooth')}</span>
      )}
      {printer.error && (
        <span role="alert" className="text-sm text-danger">
          {t('receipt.failed')}
        </span>
      )}
    </div>
  )
}
