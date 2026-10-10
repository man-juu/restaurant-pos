import { useTranslation } from 'react-i18next'

import type { Costing } from '../../lib/api/types'
import { formatMoney, formatNumber, intlLocale } from '../../lib/format'
import { useChannels } from './api'

/** FR-CAT-007: what one unit uses after expanding nested recipes, its cost and margins. */
export function CostingView({ costing, currency }: { costing: Costing; currency: string }) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const channels = useChannels()
  const money = (value: string | number) => formatMoney(Math.round(Number(value)), currency, locale)
  const channelName = (id: string) => channels.data?.find((c) => c.id === id)?.name ?? '—'

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-col gap-1">
        {costing.lines.map((ln) => (
          <li
            key={ln.item_id}
            className="flex flex-wrap justify-between gap-2 border-b border-line py-1.5"
          >
            <span>{ln.name}</span>
            <span className="tabular-nums text-ink-soft">
              {`${formatNumber(Number(ln.base_qty), locale)} ${ln.unit_code}`}
              {ln.cost !== null && ` · ${money(ln.cost)}`}
            </span>
          </li>
        ))}
      </ul>
      {costing.cost_visible && costing.cost === null && (
        <p className="text-sm text-ink-soft">{t('catalog.recipe.costUnknown')}</p>
      )}
      {costing.cost !== null && (
        <p className="font-bold">{t('catalog.recipe.cost', { cost: money(costing.cost) })}</p>
      )}
      {costing.margins.length > 0 && costing.cost !== null && (
        <ul className="grid gap-2 sm:grid-cols-2">
          {costing.margins.map((m) => (
            <li key={m.channel_id} className="rounded-xl border border-line px-3 py-2 text-sm">
              <b>{channelName(m.channel_id)}</b>
              <span className="block text-ink-soft">
                {t('catalog.recipe.margin', {
                  price: money(m.net_price),
                  margin: m.margin === null ? '—' : money(m.margin),
                  pct: m.cost_pct ?? '—',
                })}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
