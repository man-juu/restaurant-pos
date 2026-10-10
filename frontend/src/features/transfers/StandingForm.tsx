import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { CheckInput, SelectInput, TextInput } from '../../components/form'
import { Alert, Button, Card } from '../../components/ui'
import type { OutletOut, StandingOut } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { ComponentPicker } from '../catalog/ComponentPicker'
import { useSaveStanding } from './standingApi'

const QTY = /^\d{1,14}([.,]\d{1,4})?$/
const DAYS = [0, 1, 2, 3, 4, 5, 6]
type Line = { item_id: string; label: string; qty: string }
const ready = (from: string, days: number[], lines: Line[]) =>
  Boolean(from) && days.length > 0 && lines.length > 0 && lines.every((l) => QTY.test(l.qty))

function initial(current: StandingOut | undefined, firstSource: string) {
  if (!current) return { from: firstSource, days: [], lead: '1', active: true, lines: [] }
  return {
    from: current.from_outlet_id,
    days: current.weekdays,
    lead: String(current.lead_days),
    active: current.is_active,
    lines: current.lines.map((l) => ({
      item_id: l.item_id,
      label: l.name,
      qty: String(Number(l.qty)),
    })),
  }
}

/** FR-TRF-005: this outlet's regular order: weekdays, how early to ask, and what. */
export function StandingForm({
  outletId,
  outlets,
  current,
  onDone,
}: {
  outletId: string
  outlets: OutletOut[]
  current?: StandingOut
  onDone: () => void
}) {
  const { t } = useTranslation()
  const save = useSaveStanding()
  const sources = outlets.filter((o) => o.is_active && o.id !== outletId)
  const start = initial(current, sources[0]?.id ?? '')
  const [from, setFrom] = useState(start.from)
  const [days, setDays] = useState<number[]>(start.days)
  const [lead, setLead] = useState(start.lead)
  const [active, setActive] = useState(start.active)
  const [lines, setLines] = useState<Line[]>(start.lines)
  const toggle = (d: number, on: boolean) =>
    setDays(on ? [...days, d] : days.filter((x) => x !== d))
  const body = {
    from_outlet_id: from,
    to_outlet_id: outletId,
    weekdays: [...days].sort(),
    lead_days: Number.parseInt(lead, 10) || 0,
    is_active: active,
    lines: lines.map((l) => ({ item_id: l.item_id, qty: l.qty.replace(',', '.') })),
  }
  return (
    <Card className="flex flex-col gap-3">
      <SelectInput
        label={t('transfers.from')}
        value={from}
        onChange={(e) => setFrom(e.target.value)}
      >
        {sources.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </SelectInput>
      <fieldset className="flex flex-wrap gap-3">
        <legend className="text-sm font-semibold text-ink-soft">{t('standing.days')}</legend>
        {DAYS.map((d) => (
          <CheckInput
            key={d}
            label={t(`standing.weekday.${d}`)}
            checked={days.includes(d)}
            onChange={(on) => toggle(d, on)}
          />
        ))}
      </fieldset>
      <TextInput
        label={t('standing.lead')}
        inputMode="numeric"
        value={lead}
        onChange={(e) => setLead(e.target.value)}
      />
      {lines.map((l, i) => (
        <TextInput
          key={l.item_id}
          label={t('transfers.qtyOf', { name: l.label })}
          inputMode="decimal"
          value={l.qty}
          onChange={(e) =>
            setLines(lines.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))
          }
        />
      ))}
      <ComponentPicker
        exclude={new Set(lines.map((l) => l.item_id))}
        onPick={(item) => setLines([...lines, { item_id: item.id, label: item.name, qty: '' }])}
        label={t('transfers.add')}
      />
      <CheckInput label={t('standing.active')} checked={active} onChange={setActive} />
      {save.error ? <Alert>{errorMessage(save.error, t)}</Alert> : null}
      <div className="flex gap-2">
        <Button
          disabled={!ready(from, days, lines) || save.isPending}
          onClick={() => save.mutate({ id: current?.id, body }, { onSuccess: onDone })}
        >
          {t('standing.save')}
        </Button>
        <Button variant="ghost" onClick={onDone}>
          {t('catalog.back')}
        </Button>
      </div>
    </Card>
  )
}
