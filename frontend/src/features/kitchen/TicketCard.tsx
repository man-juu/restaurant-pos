import { clsx } from 'clsx'
import { useTranslation } from 'react-i18next'

import { Button, StateBadge } from '../../components/ui'
import type { TicketOut } from '../../lib/api/types'
import { useTicketStep } from './kitchenApi'

const NEXT: Record<string, 'start' | 'ready' | 'bump'> = {
  new: 'start',
  preparing: 'ready',
  ready: 'bump',
}

/** FR-KDS-001, 003, 004: one ticket with its age; late ones stand out. */
export function TicketCard({
  ticket,
  now,
  canUpdate,
}: {
  ticket: TicketOut
  now: number
  canUpdate: boolean
}) {
  const { t } = useTranslation()
  const step = useTicketStep()
  const minutes = Math.max(0, Math.floor((now - new Date(ticket.created_at).getTime()) / 60_000))
  const action = ticket.status === 'bumped' ? 'recall' : NEXT[ticket.status]
  return (
    <article
      className={clsx(
        'flex flex-col gap-2 rounded-xl border-2 bg-card p-3',
        ticket.late ? 'border-danger' : 'border-line',
      )}
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <b className="text-lg">{ticket.label ?? ticket.order_number}</b>
        <span className={clsx('tabular-nums', ticket.late && 'font-bold text-danger')}>
          {t('kitchen.minutes', { count: minutes })}
        </span>
      </header>
      <span className="flex flex-wrap gap-1 text-sm text-ink-soft">
        {ticket.order_number} · {ticket.channel_name}
        {ticket.platform && <StateBadge state="shipped" label={ticket.platform} />}
      </span>
      <ul className="flex flex-col gap-1">
        {ticket.items.map((i) => (
          <li key={i.id} className={i.status === 'void' ? 'text-ink-soft line-through' : undefined}>
            <b>{Number(i.qty)} ×</b> {i.name}
            {i.modifiers && <span className="block text-sm">{i.modifiers}</span>}
            {i.note && <span className="block text-sm font-semibold text-warn">{i.note}</span>}
          </li>
        ))}
      </ul>
      {canUpdate && action && (
        <Button disabled={step.isPending} onClick={() => step.mutate({ id: ticket.id, action })}>
          {t(`kitchen.actions.${action}`)}
        </Button>
      )}
    </article>
  )
}
