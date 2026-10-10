import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '../../components/ui'
import { request } from '../../lib/api/client'
import type { SuggestionLine, VendorScoreOut } from '../../lib/api/types'
import { formatNumber, intlLocale } from '../../lib/format'

const n = (v: string | null | undefined) => String(Number(v ?? 0))

/** One reorder line, with the order quantity and, on request, the vendors ranked
 * (FR-INV-018, FR-PUR-007). */
export function SuggestionRow({ line }: { line: SuggestionLine }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <li className="flex flex-col gap-1 border-b border-line py-1">
      <span>
        {t('purchasing.reorder.line', {
          name: line.name,
          have: n(line.on_hand),
          point: n(line.reorder_point),
          need: n(line.suggested),
          unit: line.unit_code,
        })}
      </span>
      {line.eoq && (
        <span className="text-ink-soft">
          {t('planning.eoq', { qty: n(line.eoq), unit: line.unit_code })}
        </span>
      )}
      <Button variant="ghost" className="self-start" onClick={() => setOpen(!open)}>
        {t(open ? 'planning.hideVendors' : 'planning.compareVendors')}
      </Button>
      {open && <Ranking itemId={line.item_id} unit={line.unit_code} />}
    </li>
  )
}

function Ranking({ itemId, unit }: { itemId: string; unit: string }) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const ranked = useQuery({
    queryKey: ['vendor-ranking', itemId],
    queryFn: () =>
      request<VendorScoreOut[]>('GET', `/api/v1/purchasing/vendor-ranking?item_id=${itemId}`),
  })
  if (ranked.isSuccess && ranked.data.length === 0)
    return <p className="text-ink-soft">{t('planning.noVendors')}</p>
  const pct = (v: string | null | undefined) =>
    v == null ? t('planning.noHistory') : `${formatNumber(Number(v), locale)} %`
  return (
    <ol className="flex flex-col gap-1 pl-4">
      {ranked.data?.map((s, i) => (
        <li key={s.vendor_id} className={i === 0 ? 'font-semibold' : ''}>
          {t('planning.vendorLine', {
            rank: i + 1,
            name: s.vendor_name,
            price: formatNumber(Number(s.per_base), locale),
            unit,
            lead: s.lead_days == null ? t('planning.noHistory') : n(s.lead_days),
            onTime: pct(s.on_time_pct),
            fill: pct(s.fill_pct),
          })}
          {s.preferred && ` · ${t('planning.preferred')}`}
        </li>
      ))}
    </ol>
  )
}
