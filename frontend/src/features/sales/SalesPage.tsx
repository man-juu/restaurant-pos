import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useOutletContext } from 'react-router'

import { SelectInput, TextInput } from '../../components/form'
import type { Capabilities } from '../../lib/api/types'
import { useOutlets } from '../../lib/session'
import { useChannels } from '../catalog/api'
import { todayIso } from '../catalog/labels'
import { useDay } from './api'
import { DaySummary } from './DaySummary'
import { EntryGrid } from './EntryGrid'

interface Option {
  id: string
  name: string
}

/** A select that falls back to the first option until the user picks one. */
function usePick(options: Option[] | undefined) {
  const [picked, setPicked] = useState('')
  return [picked || options?.[0]?.id || '', setPicked] as const
}

function Picker({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: Option[] | undefined
  onChange: (v: string) => void
}) {
  return (
    <SelectInput label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      {options?.map((o) => (
        <option key={o.id} value={o.id}>
          {o.name}
        </option>
      ))}
    </SelectInput>
  )
}

/** FR-SAL-002, 003: enter a day's sales per channel; lock the day after review. */
export function SalesPage() {
  const { t } = useTranslation()
  const { caps } = useOutletContext<{ caps?: Capabilities }>()
  const outlets = useOutlets().data?.filter((o) => o.is_active)
  const channels = useChannels().data
  const [outletId, setOutlet] = usePick(outlets)
  const [channelId, setChannel] = usePick(channels)
  const [on, setOn] = useState(todayIso)
  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-3xl font-extrabold">{t('sales.title')}</h1>
      <div className="grid gap-3 sm:grid-cols-3">
        <Picker
          label={t('inventory.outlet')}
          value={outletId}
          options={outlets}
          onChange={setOutlet}
        />
        <TextInput
          label={t('sales.date')}
          type="date"
          value={on}
          onChange={(e) => setOn(e.target.value)}
        />
        <Picker
          label={t('sales.channel')}
          value={channelId}
          options={channels}
          onChange={setChannel}
        />
      </div>
      {outletId && channelId && (
        <DayBody
          outletId={outletId}
          on={on}
          channelId={channelId}
          channels={channels ?? []}
          caps={caps}
        />
      )}
    </div>
  )
}

function DayBody({
  outletId,
  on,
  channelId,
  channels,
  caps,
}: {
  outletId: string
  on: string
  channelId: string
  channels: Option[]
  caps?: Capabilities
}) {
  const { i18n } = useTranslation()
  const day = useDay(outletId, on, i18n.language).data
  const has = (code: string) => Boolean(caps?.permissions.includes(code))
  const currency = caps?.currency ?? 'IDR'
  const names = Object.fromEntries(channels.map((c) => [c.id, c.name]))
  const canEnter = has('sales.day.enter') && day?.status !== 'locked'
  return (
    <>
      {day && (
        <DaySummary
          day={day}
          channels={names}
          currency={currency}
          canLock={has('sales.day.lock')}
        />
      )}
      {canEnter && (
        <EntryGrid
          key={`${outletId}${on}${channelId}`}
          outletId={outletId}
          on={on}
          channelId={channelId}
          currency={currency}
        />
      )}
    </>
  )
}
