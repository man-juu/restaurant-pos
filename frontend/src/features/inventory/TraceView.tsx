import { useTranslation } from 'react-i18next'

import { Alert, Button } from '../../components/ui'
import type { TraceBatch } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { formatDate, formatNumber, intlLocale } from '../../lib/format'
import { useTrace } from './traceApi'

export function BatchLine({ batch, outlet }: { batch: TraceBatch; outlet: string }) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  return (
    <span className="flex flex-col">
      <span className="font-semibold">{`${batch.name} · ${batch.lot_code ?? '—'}`}</span>
      <span className="text-sm text-ink-soft">
        {t('inventory.trace.batchLine', {
          outlet,
          made: formatDate(batch.received_at.slice(0, 10), locale),
          expiry: batch.expiry_date ? formatDate(batch.expiry_date, locale) : '—',
        })}
      </span>
    </span>
  )
}

function Section({
  title,
  rows,
  outletName,
}: {
  title: string
  rows: TraceBatch[]
  outletName: (id: string) => string
}) {
  const { t } = useTranslation()
  return (
    <section className="flex flex-col gap-2">
      <h3 className="font-display font-bold">{title}</h3>
      {rows.length === 0 && <p className="text-sm text-ink-soft">{t('inventory.trace.empty')}</p>}
      <ul className="flex flex-col gap-2">
        {rows.map((b) => (
          <li
            key={b.id}
            className="rounded-xl border border-line p-3"
            style={{ marginInlineStart: `${Math.min(b.depth - 1, 4)}rem` }}
          >
            <BatchLine batch={b} outlet={outletName(b.outlet_id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

type Props = { batchId: string; outletName: (id: string) => string; onBack: () => void }

export function TraceView({ batchId, outletName, onBack }: Props) {
  const { t, i18n } = useTranslation()
  const trace = useTrace(batchId, i18n.language)
  const locale = intlLocale(i18n.language)
  if (trace.error) return <Alert>{errorMessage(trace.error, t)}</Alert>
  if (!trace.data) return null
  const d = trace.data
  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between gap-2">
        <BatchLine batch={d.batch} outlet={outletName(d.batch.outlet_id)} />
        <Button variant="ghost" onClick={onBack}>
          {t('inventory.trace.back')}
        </Button>
      </div>
      <Section title={t('inventory.trace.sources')} rows={d.sources} outletName={outletName} />
      <Section title={t('inventory.trace.went')} rows={d.descendants} outletName={outletName} />
      <section className="flex flex-col gap-2">
        <h3 className="font-display font-bold">{t('inventory.trace.uses')}</h3>
        <ul className="flex flex-col gap-1 text-sm">
          {d.uses.map((u) => (
            <li key={`${u.batch_id}-${u.doc_id}`} className="flex justify-between gap-2">
              <span>
                {`${t(`inventory.trace.doc.${u.doc_type}`, { defaultValue: u.doc_type })} · ${outletName(u.outlet_id)}`}
              </span>
              <span className="tabular-nums">
                {`${formatDate(u.business_date, locale)} · ${formatNumber(Number(u.qty), locale)}`}
              </span>
            </li>
          ))}
        </ul>
      </section>
      {d.hidden > 0 && (
        <p className="text-sm text-ink-soft">{t('inventory.trace.hidden', { count: d.hidden })}</p>
      )}
    </div>
  )
}
