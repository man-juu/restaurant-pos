import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, Card } from '../../components/ui'
import type { PrepRow } from '../../lib/api/types'
import { errorMessage } from '../../lib/errors'
import { usePlan, usePrepList, prepPdfUrl } from './api'

const n = (v: string) => String(Number(v))

/** Ticks live on this phone only: a quick checklist, not a record. */
function useTicks(key: string) {
  const read = (): string[] => {
    try {
      return JSON.parse(localStorage.getItem(key) ?? '[]') as string[]
    } catch {
      return []
    }
  }
  const [ticks, setTicks] = useState(read)
  const toggle = (id: string) => {
    const next = ticks.includes(id) ? ticks.filter((x) => x !== id) : [...ticks, id]
    setTicks(next)
    try {
      localStorage.setItem(key, JSON.stringify(next))
    } catch {
      /* private mode: ticks stay in memory */
    }
  }
  return { ticks, toggle }
}

/** FR-PRD-008: what is below par today, how much to make, tick it off or plan it. */
export function PrepTab({
  outletId,
  date,
  canPlan,
}: {
  outletId: string
  date: string
  canPlan: boolean
}) {
  const { t, i18n } = useTranslation()
  const list = usePrepList(outletId, date, i18n.language)
  const { ticks, toggle } = useTicks(`prep:${outletId}:${date}`)
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-ink-soft">{t('production.prep.help')}</p>
        <a
          className="text-sm font-semibold text-accent underline"
          href={prepPdfUrl(outletId, date, i18n.language)}
          target="_blank"
          rel="noreferrer"
        >
          {t('production.prep.print')}
        </a>
      </div>
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('production.prep.empty')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {list.data?.map((row) => (
          <PrepItem
            key={row.item_id}
            row={row}
            done={ticks.includes(row.item_id)}
            onTick={() => toggle(row.item_id)}
            outletId={outletId}
            date={date}
            canPlan={canPlan}
          />
        ))}
      </ul>
    </Card>
  )
}

function PrepItem({
  row,
  done,
  onTick,
  outletId,
  date,
  canPlan,
}: {
  row: PrepRow
  done: boolean
  onTick: () => void
  outletId: string
  date: string
  canPlan: boolean
}) {
  const { t } = useTranslation()
  const plan = usePlan()
  const [key] = useState(() => crypto.randomUUID())
  const todo = Number(row.suggested) > 0
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-xl border border-line p-3">
      <label className="flex flex-1 items-center gap-3">
        <input type="checkbox" className="size-5" checked={done} onChange={onTick} />
        <span className={done ? 'text-ink-soft line-through' : 'font-semibold'}>
          {row.name}
          <span className="block text-sm font-normal text-ink-soft">
            {t('production.prep.line', {
              make: n(row.suggested),
              unit: row.unit_code,
              have: n(row.on_hand),
              par: n(row.par_qty),
              requested: n(row.requested ?? '0'),
              planned: n(row.planned),
            })}
          </span>
        </span>
      </label>
      {canPlan && todo && (
        <Button
          variant="ghost"
          disabled={plan.isPending || plan.isSuccess}
          onClick={() =>
            plan.mutate({
              body: {
                outlet_id: outletId,
                item_id: row.item_id,
                planned_qty: row.suggested,
                production_date: date,
              },
              key,
            })
          }
        >
          {t('production.prep.plan')}
        </Button>
      )}
      {plan.error ? <Alert>{errorMessage(plan.error, t)}</Alert> : null}
    </li>
  )
}
