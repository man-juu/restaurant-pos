import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Alert, Card } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { ProducibleRow } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatNumber, intlLocale } from '../../lib/format'

const useProducible = (outletId: string, lang: string) =>
  useQuery({
    queryKey: ['producible', outletId, lang],
    queryFn: () =>
      request<ProducibleRow[]>(
        'GET',
        `/api/v1/inventory/producible?outlet_id=${outletId}&lang=${lang.slice(0, 2)}`,
      ),
  })

/** FR-INV-020: what the stock here can still make, fewest first, and what runs out first. */
export function ProducibleTab({ outletId }: { outletId: string }) {
  const { t, i18n } = useTranslation()
  const list = useProducible(outletId, i18n.language)
  const locale = intlLocale(i18n.language)
  return (
    <Card className="flex flex-col gap-3">
      <p className="text-sm text-ink-soft">{t('inventory.producible.help')}</p>
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('inventory.producible.empty')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {list.data?.map((r) => (
          <li
            key={r.item_id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line p-3"
          >
            <span className="font-semibold">{r.name}</span>
            <span className="text-right tabular-nums">
              <span className={Number(r.can_make) === 0 ? 'font-bold text-danger' : 'font-bold'}>
                {`${formatNumber(Number(r.can_make), locale)} ${r.unit_code}`}
              </span>
              {r.limiting_name && (
                <span className="block text-xs text-ink-soft">
                  {t('inventory.producible.limit', { name: r.limiting_name })}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  )
}
