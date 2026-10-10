import { type FormEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card, Field } from '../../components/ui'
import { errorMessage } from '../../lib/errors'
import { useOutlets } from '../../lib/session'
import { useLots } from './traceApi'
import { BatchLine, TraceView } from './TraceView'

/** FR-INV-016: find a batch by its lot code, then see where it came from and went. */
export function TraceTab() {
  const { t, i18n } = useTranslation()
  const [draft, setDraft] = useState('')
  const [lot, setLot] = useState('')
  const [picked, setPicked] = useState<string | null>(null)
  const lots = useLots(lot, i18n.language)
  const outlets = useOutlets('inventory')
  const outletName = (id: string) => outlets.data?.find((o) => o.id === id)?.name ?? ''
  const search = (e: FormEvent) => {
    e.preventDefault()
    setPicked(null)
    setLot(draft.trim())
  }
  return (
    <Card className="flex flex-col gap-4">
      <p className="text-sm text-ink-soft">{t('inventory.trace.help')}</p>
      <form className="flex flex-wrap items-end gap-2" onSubmit={search}>
        <Field
          label={t('inventory.trace.lot')}
          value={draft}
          maxLength={64}
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button type="submit" disabled={!draft.trim()}>
          {t('inventory.trace.search')}
        </Button>
      </form>
      {lots.error && <Alert>{errorMessage(lots.error, t)}</Alert>}
      {lots.isSuccess && lots.data.length === 0 && (
        <p className="text-ink-soft">{t('inventory.trace.none')}</p>
      )}
      {!picked && (
        <ul className="flex flex-col gap-2">
          {lots.data?.map((b) => (
            <li key={b.id}>
              <button
                type="button"
                className="w-full rounded-xl border border-line p-3 text-left hover:bg-raised"
                onClick={() => setPicked(b.id)}
              >
                <BatchLine batch={b} outlet={outletName(b.outlet_id)} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {picked && (
        <TraceView batchId={picked} outletName={outletName} onBack={() => setPicked(null)} />
      )}
    </Card>
  )
}
