import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Alert, Button, StateBadge } from '../../../components/ui'
import type { GlAccountOut, JournalOut } from '../../../lib/api/types'
import { errorMessage } from '../../../lib/errors'
import { formatDate, formatMoney, intlLocale } from '../../../lib/format'
import { JournalForm } from './JournalForm'
import { useGlAction, useJournals } from './glApi'

type Props = {
  from: string
  to: string
  currency: string
  accounts: GlAccountOut[]
  canPost: boolean
}

/** FR-FIN-002, 004: journals in the period; approve, reject or reverse. */
export function JournalsView({ from, to, currency, accounts, canPost }: Props) {
  const { t } = useTranslation()
  const list = useJournals(from, to)
  const [adding, setAdding] = useState(false)
  const name = (id: string) => {
    const a = accounts.find((x) => x.id === id)
    return a ? `${a.code} ${a.name}` : ''
  }
  return (
    <div className="flex flex-col gap-3">
      {canPost && !adding && (
        <Button className="self-start" onClick={() => setAdding(true)}>
          {t('books.newJournal')}
        </Button>
      )}
      {adding && (
        <JournalForm accounts={accounts} currency={currency} onDone={() => setAdding(false)} />
      )}
      {list.error && <Alert>{errorMessage(list.error, t)}</Alert>}
      {list.isSuccess && list.data.length === 0 && (
        <p className="text-ink-soft">{t('books.noJournals')}</p>
      )}
      <ul className="flex flex-col gap-2">
        {list.data?.map((e) => (
          <Entry key={e.id} e={e} name={name} currency={currency} canPost={canPost} />
        ))}
      </ul>
    </div>
  )
}

function Entry({
  e,
  name,
  currency,
  canPost,
}: {
  e: JournalOut
  name: (id: string) => string
  currency: string
  canPost: boolean
}) {
  const { t, i18n } = useTranslation()
  const locale = intlLocale(i18n.language)
  const act = useGlAction()
  const money = (v: number) => (v ? formatMoney(v, currency, locale) : '')
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-line bg-card p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-bold">{`${e.number} · ${formatDate(e.entry_date, locale)} · ${e.memo ?? t(`books.source.${e.source_doc_type}`, { defaultValue: e.source_doc_type })}`}</p>
        <StateBadge state={e.status} label={t(`books.status.${e.status}`)} />
      </div>
      <table className="text-sm">
        <tbody>
          {e.lines.map((l, i) => (
            <tr key={i}>
              <td className="pr-2">{name(l.account_id)}</td>
              <td className="text-right tabular-nums">{money(l.debit)}</td>
              <td className="text-right tabular-nums">{money(l.credit)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {canPost && e.status === 'submitted' && (
        <div className="flex gap-2">
          <Button
            disabled={act.isPending}
            onClick={() => act.mutate({ path: `journals/${e.id}/approve` })}
          >
            {t('books.approve')}
          </Button>
          <Button
            variant="ghost"
            disabled={act.isPending}
            onClick={() => act.mutate({ path: `journals/${e.id}/reject` })}
          >
            {t('books.reject')}
          </Button>
        </div>
      )}
      {canPost && e.status === 'posted' && !e.reverses_id && (
        <Button
          variant="ghost"
          className="self-start"
          disabled={act.isPending}
          onClick={() =>
            act.mutate({
              path: `journals/${e.id}/reverse`,
              body: { entry_date: new Date().toISOString().slice(0, 10) },
            })
          }
        >
          {t('books.reverse')}
        </Button>
      )}
      {act.error && <Alert>{errorMessage(act.error, t)}</Alert>}
    </li>
  )
}
