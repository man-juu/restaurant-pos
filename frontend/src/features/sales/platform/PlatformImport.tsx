import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { ImportPanel } from '../../../components/imports/ImportPanel'
import { Button } from '../../../components/ui'
import type { ImportCheck, PlatformCheckOut } from '../../../lib/api/types'
import { formatMoney, intlLocale } from '../../../lib/format'
import { IMPORTS } from '../../../lib/imports'
import { useColumnMap } from './api'
import { MappingForm } from './MappingForm'

/** FR-IMP-004: a delivery platform's sales export becomes the days' sales for this outlet
 * and channel (stock out by recipe), checked first, all rows or none. */
export function PlatformImport(props: { outletId: string; channelId: string; currency: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const map = useColumnMap(props.channelId)
  if (!open)
    return (
      <Button variant="ghost" onClick={() => setOpen(true)}>
        {t('sales.platform.open')}
      </Button>
    )
  if (map.data === undefined) return null
  const mapping = !map.data || editing
  return (
    <ImportPanel
      key={props.channelId}
      kind={IMPORTS.platform}
      template={false}
      title={t('sales.platform.title')}
      help={t('sales.platform.help')}
      options={{ outlet_id: props.outletId, channel_id: props.channelId }}
      onClose={() => setOpen(false)}
      extra={(data) => <Days data={data} currency={props.currency} />}
    >
      {mapping ? (
        <MappingForm
          channelId={props.channelId}
          saved={map.data}
          onSaved={() => setEditing(false)}
        />
      ) : (
        <Button variant="ghost" onClick={() => setEditing(true)}>
          {t('sales.platform.editMap')}
        </Button>
      )}
    </ImportPanel>
  )
}

function Days({ data, currency }: { data: ImportCheck; currency: string }) {
  const { t, i18n } = useTranslation()
  const days = (data as unknown as PlatformCheckOut).days ?? []
  return (
    <ul className="text-sm">
      {days.map((d) => (
        <li key={d.business_date}>
          {d.business_date}: {formatMoney(d.total, currency, intlLocale(i18n.language))}
          {d.replaces && <span className="text-warn"> · {t('sales.platform.replaces')}</span>}
        </li>
      ))}
    </ul>
  )
}
